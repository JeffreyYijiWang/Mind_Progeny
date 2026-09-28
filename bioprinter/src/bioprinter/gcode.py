from __future__ import annotations
from dataclasses import dataclass, asdict
import math
import re


@dataclass
class Motion:
    start: tuple[float,float,float]
    end: tuple[float,float,float]
    e_delta: float = 0
    feed: float = 0  # mm/min for XYZ; E units/min for an E-only move
    dwell: float = 0
    kind: str = "travel"
    source_line: int = 0
    event: str = ""
    source: str = ""

    @property
    def length(self): return math.dist(self.start,self.end)
    def dict(self): return asdict(self)


class GCodeError(ValueError):
    def __init__(self, message, report):
        super().__init__(message)
        self.report=report


THERMAL_FAN={"M104","M109","M140","M190","M106","M107","M141","M191","M116","M568",
             "M143","M144","M307","M308","M303","M301","M570"}
FINAL_ALLOW={"G21","G90","M83","G1","G4"}
TOKEN=re.compile(r"([A-Za-z])([-+]?(?:\d*\.\d+|\d+\.?\d*))")


def lex(line):
    # Parse comments, then tokenize all remaining bytes; never substring-delete commands.
    out=[];depth=0
    for ch in line:
        if ch==';' and depth==0: break
        if ch=='(':
            if depth: raise ValueError("Nested comments unsupported")
            depth=1
        elif ch==')':
            if not depth: raise ValueError("Unmatched comment")
            depth=0
        elif not depth: out.append(ch)
    if depth: raise ValueError("Unclosed comment")
    raw=''.join(out).strip()
    if not raw: return None,{}
    tokens=[];pos=0
    while pos<len(raw):
        if raw[pos].isspace(): pos+=1;continue
        match=TOKEN.match(raw,pos)
        if not match: raise ValueError("Expressions, checksums, strings or malformed tokens unsupported")
        letter,value=match.groups(); tokens.append((letter.upper(),float(value)));pos=match.end()
    letter,value=tokens.pop(0)
    if letter not in "GMT" or not value.is_integer(): raise ValueError("Expected one integer G/M/T command per line")
    cmd=letter+str(int(value));params={}
    for letter,value in tokens:
        if letter in params or letter in "GMTN": raise ValueError("Multiple commands/duplicate parameters/line numbers unsupported")
        if not math.isfinite(value): raise ValueError("Nonfinite number")
        params[letter]=value
    return cmd,params


def interpret(text, *, initial=(0.,0.,0.), final_policy=False, e_units='filament_mm'):
    if e_units not in {'filament_mm','mm3','syringe'}: raise ValueError('Unknown extrusion units')
    pos=list(initial); offsets=[0.,0.,0.];e=0.;e_abs=True;xyz_abs=True;unit=1.;feed=0.
    motions=[];report=[]
    for number,line in enumerate(text.splitlines(),1):
        try:
            cmd,p=lex(line)
            if cmd is None: continue
            if final_policy and cmd not in FINAL_ALLOW: raise ValueError(f"Not in final allowlist: {cmd}")
            if cmd in THERMAL_FAN:
                report.append({"line":number,"command":cmd,"action":"removed","reason":"thermal/fan policy"});continue
            if cmd=='M950':
                if set(p)&{'H','F'} and not set(p)&{'S','J','P'}:
                    report.append({"line":number,"command":cmd,"action":"removed","reason":"heater/fan port configuration"});continue
                raise ValueError('Nonthermal or mixed M950 requires explicit machine-configuration review')
            if cmd=="G10":
                if (set(p)&{"S","R"}) and set(p)<={"P","S","R"}:
                    report.append({"line":number,"command":cmd,"action":"removed","reason":"RRF tool temperature parameters"});continue
                raise ValueError("Nonthermal/mixed G10 requires explicit offset or firmware-retraction support")
            if cmd in {"G20","G21","G90","G91","M82","M83"}:
                if p: raise ValueError("Unexpected modal parameters")
                if cmd=="G20":
                    if e_units=='mm3': raise ValueError('Volumetric inch input unsupported; export G21 millimeter/volume input')
                    unit=25.4
                if cmd=="G21": unit=1.
                # RepRapFirmware: axes and extruder positioning modes are independent.
                if cmd=="G90": xyz_abs=True
                if cmd=="G91": xyz_abs=False
                if cmd=="M82": e_abs=True
                if cmd=="M83": e_abs=False
                report.append({"line":number,"command":cmd,"action":"normalized"});continue
            if cmd=="G92":
                if not p or set(p)-set("XYZE"): raise ValueError("Only explicit G92 XYZ/E supported")
                for i,axis in enumerate("XYZ"):
                    if axis in p: offsets[i]=pos[i]-p[axis]*unit
                if "E" in p: e=p["E"]*unit
                report.append({"line":number,"command":cmd,"action":"resolved-reset"});continue
            if cmd=="G4":
                if len(p)!=1 or not set(p)<={"P","S"}: raise ValueError("G4 requires exactly P milliseconds or S seconds")
                duration=p.get("S",p.get("P",0)/1000)
                if duration<0: raise ValueError("Negative dwell")
                motions.append(Motion(tuple(pos),tuple(pos),dwell=duration,kind="dwell",source_line=number));continue
            if cmd not in {"G0","G1"}:
                if cmd in {"G2","G3"}: raise ValueError("Arcs unsupported: export/tessellate to G1 before import")
                raise ValueError(f"Unreviewed command {cmd}; macro/tool/machine commands never pass through")
            if set(p)-set("XYZEF"): raise ValueError("Unsupported motion parameter")
            if "F" in p:
                feed=p["F"]*unit
                if feed<=0: raise ValueError("Feedrate must be positive")
            new=pos.copy()
            for i,axis in enumerate("XYZ"):
                if axis in p: new[i]=p[axis]*unit+(offsets[i] if xyz_abs else pos[i])
            new_e=e
            if "E" in p: new_e=p["E"]*unit+(0 if e_abs else e)
            delta=new_e-e
            if new!=pos or delta:
                if feed<=0: raise ValueError("Motion before explicit positive feedrate")
                kind="retract" if delta<0 else "deposit" if delta>0 and new[:2]!=pos[:2] else "prime" if delta>0 else "travel"
                motions.append(Motion(tuple(pos),tuple(new),delta,feed,kind=kind,source_line=number))
            pos=new;e=new_e
        except ValueError as exc:
            report.append({"line":number,"action":"rejected","reason":str(exc)})
            raise GCodeError(f"G-code line {number}: {exc}",report) from exc
    return motions,report


def serialize(motions, *, preview=True, initial=None):
    header=["; BIOPRINTER " + ("PREVIEW ONLY - SYNTHETIC/UNAPPROVED" if preview else "PRODUCTION - preflight required"),
            "; mm, absolute XYZ in centered machine frame; relative calibrated E", "G21","G90","M83"]
    lines=header[:];ranges=[];offset=sum(len((line+'\n').encode('ascii')) for line in lines)
    for motion in motions:
        if motion.dwell:
            line=f"G4 S{motion.dwell:.8f}"
        else:
            x,y,z=motion.end
            line=f"G1 X{x:.6f} Y{y:.6f} Z{z:.6f}"
            if motion.e_delta: line+=f" E{motion.e_delta:.9f}"
            line+=f" F{motion.feed:.6f}"
        data=(line+'\n').encode('ascii')
        ranges.append({"line":len(lines)+1,"byte_start":offset,"byte_end":offset+len(data),
                       "source_line":motion.source_line,"source":motion.source,"event":motion.event})
        lines.append(line);offset+=len(data)
    content=('\n'.join(lines)+'\n').encode('ascii')
    # Every exported executable line is parsed again against the stricter output policy.
    parsed,_=interpret(content.decode('ascii'),initial=initial or (motions[0].start if motions else (0,0,0)),final_policy=True)
    if len(parsed)!=len(motions): raise ValueError("Rounding removed a motion; increase feature/sample resolution")
    for a,b in zip(motions,parsed):
        if math.dist(a.end,b.end)>1e-5 or abs(a.e_delta-b.e_delta)>1e-8:
            raise ValueError("Serialization changed motion geometry/volume")
    return content,ranges,parsed
