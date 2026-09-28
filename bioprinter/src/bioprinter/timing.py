import math


def duration(motion,profile):
    """Trapezoidal acceleration, full stop at each block (conservative zero-lookahead)."""
    if motion.dwell: return motion.dwell
    d=[abs(b-a) for a,b in zip(motion.start,motion.end)]+[abs(motion.e_delta)]
    length=motion.length or d[3]
    if length==0: return 0
    speeds=[profile.xy_speed_mm_s]*2+[profile.z_speed_mm_s,profile.e_speed_units_s]
    accels=[profile.xy_accel_mm_s2]*2+[profile.z_accel_mm_s2,profile.e_accel_units_s2]
    speed=min([motion.feed/60]+[s*length/x for s,x in zip(speeds,d) if x>0])
    accel=min(a*length/x for a,x in zip(accels,d) if x>0)
    if speed<=0 or accel<=0: raise ValueError("Positive speed/acceleration required")
    return 2*math.sqrt(length/accel) if length<=speed*speed/accel else length/speed+speed/accel


def estimate(motions,profile):
    times=[0.];totals={"motion_s":0.,"dwell_s":0.,"transition_s":0.}
    for m in motions:
        seconds=duration(m,profile)
        if seconds<=0: raise ValueError("Timeline contains a zero-duration move")
        times.append(times[-1]+seconds)
        totals["dwell_s" if m.dwell else "motion_s" if m.e_delta else "transition_s"]+=seconds
    return {**totals,"total_s":times[-1],"boundaries_s":times,"transfer_s":None,
            "status":"estimated","model":"trapezoidal-full-stop-per-block-v1",
            "uncertainty":"Uncalibrated; no numeric accuracy claim. Zero junction speed overestimates ideal lookahead; pressure and firmware overhead may add time."}


def timeline(events,motions,ranges,profile,gcode_hash):
    timing=estimate(motions,profile);times=timing.pop("boundaries_s");out=[]
    for event in events:
        a,b=event["motion_start"],event["motion_end"]
        deposit=[i for i in range(a,b) if motions[i].e_delta]
        item={**event,"job_id":f"job-{len(out)+1:04d}","start_s":times[a],"end_s":times[b],
              "duration_s":times[b]-times[a],"display_action":"show",
              "deposition_start_s":times[deposit[0]],"deposition_end_s":times[deposit[-1]+1],
              "transition_s":sum(times[i+1]-times[i] for i in range(a,b) if not motions[i].e_delta and not motions[i].dwell),
              "dwell_s":sum(motions[i].dwell for i in range(a,b)),
              "line_start":ranges[a]["line"],"line_end":ranges[b-1]["line"],
              "byte_start":ranges[a]["byte_start"],"byte_end":ranges[b-1]["byte_end"],
              "timing_status":"estimated","observed_start_s":None,"observed_end_s":None}
        out.append(item)
    result={"schema_version":"1.0","origin":"first motion of combined file; modal prologue modeled as zero time",
            "gcode_sha256":gcode_hash,"ranges":"1-based inclusive lines; zero-based half-open byte offsets in combined file",
            "policy":"show at segment start; hold through outgoing lift; retain last frame after end",
            "timing":timing,"events":out}
    validate_timeline(result)
    return result


def validate_timeline(data):
    cursor=0
    for e in data["events"]:
        if abs(e["start_s"]-cursor)>1e-7 or e["duration_s"]<=0 or abs(e["end_s"]-e["start_s"]-e["duration_s"])>1e-7:
            raise ValueError("Timeline has a gap, overlap, or invalid duration")
        if e["byte_end"]<=e["byte_start"]: raise ValueError("Empty byte interval")
        cursor=e["end_s"]
    if abs(cursor-data["timing"]["total_s"])>1e-7: raise ValueError("Timeline does not cover the complete job")
