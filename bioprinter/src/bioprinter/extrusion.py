from dataclasses import replace
import math


class Reservoir:
    def __init__(self, profile, used_mm3=0):
        self.profile=profile;self.used_mm3=used_mm3
        if used_mm3<0: raise ValueError("Negative reservoir use")

    def consume(self, volume):
        if volume<0: raise ValueError("Retraction is not a syringe refill")
        p=self.profile
        next_volume=self.used_mm3+volume
        stroke=next_volume/p.mm3_per_e_unit*p.plunger_mm_per_e_unit
        if next_volume>p.capacity_mm3+1e-8 or stroke>p.plunger_stroke_mm+1e-8:
            raise ValueError(f"Syringe capacity/stroke exceeded: {next_volume:.3f} mm3")
        self.used_mm3=next_volume
        return volume/p.mm3_per_e_unit*p.positive_extrusion_direction


def convert_slicer(motions, profile, used_mm3=0):
    reservoir=Reservoir(profile,used_mm3);result=[];report=[]
    area=math.pi*(profile.slicer_filament_diameter_mm/2)**2
    for m in motions:
        if m.kind in {"retract","prime"}:
            # Positive prime is also omitted: it needs its own liquid pressure calibration.
            report.append({"line":m.source_line,"action":"removed","reason":"uncalibrated liquid prime/retraction"})
            if m.length: result.append(replace(m,e_delta=0,kind="travel"))
            continue
        volume=m.e_delta*(area if profile.slicer_e_mode=="filament_mm" else 1)
        result.append(replace(m,e_delta=reservoir.consume(volume)))
    return result,{"volume_mm3":reservoir.used_mm3-used_mm3,"report":report}
