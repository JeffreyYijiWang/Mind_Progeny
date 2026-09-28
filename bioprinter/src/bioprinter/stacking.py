from __future__ import annotations
from dataclasses import dataclass, field
import math
import numpy as np
from shapely.geometry import LineString
from .gcode import Motion
from .extrusion import Reservoir


class CollisionError(ValueError):
    def __init__(self,message,location=None):
        super().__init__(message)
        self.location=location


class HeightField:
    """Conservative cell occupancy: capsules expanded by half the cell diagonal."""
    def __init__(self,p):
        self.p=p;self.step=p.grid_mm
        self.x=np.arange(p.x_min+self.step/2,p.x_max,self.step)
        self.y=np.arange(p.y_min+self.step/2,p.y_max,self.step)
        self.z=np.full((len(self.y),len(self.x)),p.substrate_z_mm,dtype=float)

    def cells(self,a,b,radius):
        radius+=self.step/math.sqrt(2)
        ix0=max(0,int(math.floor((min(a[0],b[0])-radius-self.p.x_min)/self.step)))
        ix1=min(len(self.x),int(math.ceil((max(a[0],b[0])+radius-self.p.x_min)/self.step)))
        iy0=max(0,int(math.floor((min(a[1],b[1])-radius-self.p.y_min)/self.step)))
        iy1=min(len(self.y),int(math.ceil((max(a[1],b[1])+radius-self.p.y_min)/self.step)))
        yy,xx=np.meshgrid(self.y[iy0:iy1],self.x[ix0:ix1],indexing="ij")
        dx=b[0]-a[0];dy=b[1]-a[1];norm=dx*dx+dy*dy
        t=np.clip(((xx-a[0])*dx+(yy-a[1])*dy)/norm,0,1) if norm else 0
        mask=(xx-(a[0]+t*dx))**2+(yy-(a[1]+t*dy))**2<=radius*radius
        return (slice(iy0,iy1),slice(ix0,ix1)),mask

    def maximum(self,a,b,radius,values=None):
        sl,mask=self.cells(a,b,radius);v=(self.z if values is None else values)[sl][mask]
        return float(v.max()) if v.size else self.p.substrate_z_mm

    def check_pose(self,a,b,z):
        p=self.p
        for point in (a,b):
            if not p.x_min+p.holder_radius_mm<=point[0]<=p.x_max-p.holder_radius_mm or not p.y_min+p.holder_radius_mm<=point[1]<=p.y_max-p.holder_radius_mm:
                raise CollisionError(f"Tool envelope leaves XY bounds at {point}",(*point[:2],z))
        if not p.z_min<=z<=p.z_max: raise CollisionError(f"Z {z:.3f} outside measured limits",(*a[:2],z))
        if self.maximum(a,b,p.needle_outer_diameter_mm/2)>z+1e-7:
            raise CollisionError(f"Needle collision at {a}->{b}, tip Z={z:.3f}; lift, relocate, or change order",(*a[:2],z))
        if self.maximum(a,b,p.holder_radius_mm)>z+p.holder_bottom_above_tip_mm+1e-7:
            raise CollisionError(f"Holder cannot access valley at {a}->{b}, Z={z:.3f}; use longer clearance tool or change design",(*a[:2],z))

    def save(self,path):
        np.savez_compressed(path,x=self.x,y=self.y,surface_z_mm=self.z,grid_mm=self.step)


@dataclass
class Plan:
    motions: list = field(default_factory=list)
    events: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)
    used_mm3: float = 0


class Planner:
    def __init__(self,profile,mode="overlap_aware",checkpoint_dir=None):
        profile.require()
        if mode not in {"overlap_aware","planar_stack"}: raise ValueError("Invalid stack mode")
        self.p=profile;self.mode=mode;self.field=HeightField(profile);self.plan=Plan()
        self.reservoir=Reservoir(profile);self.checkpoint_dir=checkpoint_dir
        # Operator must place/have homed the machine at this exact precondition.
        self.position=(0.,0.,profile.substrate_z_mm+profile.travel_clearance_mm)
        self.initial=self.position
        self.field.check_pose(self.position,self.position,self.position[2])

    def move(self,end,feed,event,kind="travel",e=0,source_line=0,source=""):
        end=tuple(float(x) for x in end)
        if math.dist(self.position,end)<1e-9 and abs(e)<1e-12: return
        self.field.check_pose(self.position,end,min(self.position[2],end[2]))
        distance=math.dist(self.position,end) or abs(e)
        deltas=[abs(b-a) for a,b in zip(self.position,end)]+[abs(e)]
        speeds=[self.p.xy_speed_mm_s,self.p.xy_speed_mm_s,self.p.z_speed_mm_s,self.p.e_speed_units_s]
        feed=min([feed]+[60*limit*distance/delta for limit,delta in zip(speeds,deltas) if delta])
        self.plan.motions.append(Motion(self.position,end,e,feed,kind=kind,event=event,source_line=source_line,source=source))
        self.position=end

    def relocate(self,xy,z,event):
        p=self.p
        # Global maximum is conservative for travel, including cross-quadrant motion.
        clearance=max(float(self.field.z.max())+p.travel_clearance_mm,z+p.travel_clearance_mm,self.position[2])
        if clearance>p.z_max: raise CollisionError("Required travel clearance exceeds Z maximum")
        self.move((self.position[0],self.position[1],clearance),p.z_speed_mm_s*60,event)
        self.move((*xy,clearance),p.xy_speed_mm_s*60,event)
        self.move((*xy,z),p.z_speed_mm_s*60,event)

    def add(self,paths,event,allowed):
        p=self.p;eid=event["event_id"];snapshot=self.field.z.copy();first=len(self.plan.motions)
        used_before=self.reservoir.used_mm3;start=self.position;support_issues=0
        for path in paths:
            footprint=LineString(path.points).buffer(p.bead_width_mm*p.spread_factor/2)
            if not allowed.covers(footprint): raise CollisionError(f"Full bead footprint leaves {event['quadrant']}")
            for a,b in zip(path.points,path.points[1:]):
                length=math.dist(a,b)
                if length<1e-9: continue
                count=max(1,math.ceil(length/p.sample_mm))
                for i in range(count):
                    u=tuple(a[j]+(b[j]-a[j])*i/count for j in (0,1))
                    v=tuple(a[j]+(b[j]-a[j])*(i+1)/count for j in (0,1))
                    radius=p.bead_width_mm*p.spread_factor/2
                    sl,mask=self.field.cells(u,v,radius);under=snapshot[sl][mask]
                    support=float(under.max()) if under.size else p.substrate_z_mm
                    if self.mode=="planar_stack":
                        support=p.substrate_z_mm+event["nominal_layer_index"]*p.deposition_height_mm
                    if under.size and (float(under.max()-under.min())>1e-6 or support-float(under.min())>1e-6): support_issues+=1
                    # Adjacent footprints union within this pass; repeats in later events add height.
                    nominal_surface=support+p.deposition_height_mm
                    z=support+p.first_deposition_tip_height_mm+p.needle_standoff_mm
                    # New material in the same pass can require a higher tip; flag the mismatch.
                    current=self.field.maximum(u,v,p.needle_outer_diameter_mm/2)
                    if current>z:
                        z=current+p.needle_standoff_mm
                        support_issues+=1
                    if math.dist(self.position[:2],u)>1e-7 or abs(self.position[2]-z)>1e-7:
                        self.relocate(u,z,eid)
                    e=self.reservoir.consume(length/count*path.volume_per_mm)
                    self.move((*v,z),min(p.deposition_speed_mm_s,p.xy_speed_mm_s)*60,eid,"deposit",e,path.source_line,event["asset_id"])
                    cells=self.field.z[sl]
                    # Add material to each occupied cell's own previous surface. Using
                    # a capsule's maximum for every cell would spread a tall step into
                    # empty neighboring cells repeatedly as the path advances.
                    surface = snapshot[sl][mask]+p.deposition_height_mm if self.mode=='overlap_aware' else nominal_surface
                    cells[mask]=np.maximum(cells[mask],surface)
        if len(self.plan.motions)==first: raise ValueError("Empty event")
        dep_end=len(self.plan.motions)
        # Allocate outgoing lift to the current image. Next-image relocation belongs to next segment.
        clearance=float(self.field.z.max())+p.travel_clearance_mm
        self.move((self.position[0],self.position[1],max(clearance,self.position[2])),p.z_speed_mm_s*60,eid)
        event={**event,"motion_start":first,"motion_end":len(self.plan.motions),"deposition_motion_end":dep_end,
               "start_xyz":start,"end_xyz":self.position,"used_before_mm3":used_before,
               "used_after_mm3":self.reservoir.used_mm3,"mode":self.mode}
        self.plan.events.append(event);self.plan.used_mm3=self.reservoir.used_mm3
        if support_issues:
            self.plan.diagnostics.append({"event":eid,"severity":"production-blocking","issue":"partially supported/variable-height footprint",
                "sample_count":support_issues,"reason":"Model cannot establish continuous liquid support; change paths/order or validate a richer model"})
        if self.checkpoint_dir:
            self.field.save(self.checkpoint_dir/f"{len(self.plan.events):04d}_{eid}.npz")
        return event
