from shapely.geometry import box
from .geometry import apply

QUADRANTS={"Q1":(0,0,60,125),"Q2":(0,-125,60,0),"Q3":(-60,-125,0,0),"Q4":(-60,0,0,125)}
FOLDERS={"Q1":"01_top_right","Q2":"02_bottom_right","Q3":"03_bottom_left","Q4":"04_top_left"}


def schedule(sequences, mode="round_robin", order=("Q1","Q2","Q3","Q4")):
    if len(set(order))!=len(order) or set(order)!=set(QUADRANTS): raise ValueError("Order must contain each quadrant once")
    if set(sequences)-set(QUADRANTS): raise ValueError("Unknown quadrant")
    if mode=="complete_stack": return [(q,i,a) for q in order for i,a in enumerate(sequences.get(q,[]))]
    if mode!="round_robin": raise ValueError("Invalid schedule")
    return [(q,i,sequences[q][i]) for i in range(max(map(len,sequences.values()),default=0))
            for q in order if i<len(sequences.get(q,[]))]


def placement(common_bounds, quadrant, profile):
    x0,y0,x1,y1=QUADRANTS[quadrant]
    # Reserve both machine envelope and centerline/outer-plate margins.
    margin=max(profile.edge_margin_mm,profile.centerline_margin_mm,profile.holder_radius_mm)
    allowed=box(max(x0,profile.x_min)+margin,max(y0,profile.y_min)+margin,
                min(x1,profile.x_max)-margin,min(y1,profile.y_max)-margin)
    ax0,ay0,ax1,ay1=allowed.bounds; bx0,by0,bx1,by1=common_bounds
    dx=(ax0+ax1-bx0-bx1)/2;dy=(ay0+ay1-by0-by1)/2
    matrix=[[1,0,dx],[0,1,dy],[0,0,1]]
    if not allowed.covers(apply(box(*common_bounds),matrix)):
        raise ValueError(f"Stack bounds {common_bounds} do not fit {quadrant}; set a smaller common physical size")
    return matrix,allowed
