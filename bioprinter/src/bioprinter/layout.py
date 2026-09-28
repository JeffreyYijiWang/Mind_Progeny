from shapely.geometry import box
from .geometry import apply

QUADRANTS=("Q1","Q2","Q3","Q4")
FOLDERS={"Q1":"01_top_right","Q2":"02_bottom_right","Q3":"03_bottom_left","Q4":"04_top_left"}


def quadrant_bounds(profile):
    if not profile.x_min<0<profile.x_max or not profile.y_min<0<profile.y_max:
        raise ValueError('Four-quadrant layout requires XY bounds spanning the centered origin')
    return {"Q1":(0,0,profile.x_max,profile.y_max),
            "Q2":(0,profile.y_min,profile.x_max,0),
            "Q3":(profile.x_min,profile.y_min,0,0),
            "Q4":(profile.x_min,0,0,profile.y_max)}


def schedule(sequences, mode="round_robin", order=("Q1","Q2","Q3","Q4")):
    if len(set(order))!=len(order) or set(order)!=set(QUADRANTS): raise ValueError("Order must contain each quadrant once")
    if set(sequences)-set(QUADRANTS): raise ValueError("Unknown quadrant")
    if mode=="complete_stack": return [(q,i,a) for q in order for i,a in enumerate(sequences.get(q,[]))]
    if mode!="round_robin": raise ValueError("Invalid schedule")
    return [(q,i,sequences[q][i]) for i in range(max(map(len,sequences.values()),default=0))
            for q in order if i<len(sequences.get(q,[]))]


def placement(common_bounds, quadrant, profile):
    x0,y0,x1,y1=quadrant_bounds(profile)[quadrant]
    # Reserve both machine envelope and centerline/outer-plate margins.
    margin=max(profile.edge_margin_mm,profile.centerline_margin_mm,profile.holder_radius_mm)
    if x1-x0<=2*margin or y1-y0<=2*margin:
        raise ValueError(f'Margins leave no usable space in {quadrant}')
    allowed=box(x0+margin,y0+margin,x1-margin,y1-margin)
    ax0,ay0,ax1,ay1=allowed.bounds; bx0,by0,bx1,by1=common_bounds
    dx=(ax0+ax1-bx0-bx1)/2;dy=(ay0+ay1-by0-by1)/2
    matrix=[[1,0,dx],[0,1,dy],[0,0,1]]
    if not allowed.covers(apply(box(*common_bounds),matrix)):
        raise ValueError(f"Stack bounds {common_bounds} do not fit {quadrant}; set a smaller common physical size")
    return matrix,allowed
