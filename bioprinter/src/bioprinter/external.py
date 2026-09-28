import importlib.metadata
import os
from pathlib import Path
import platform
import shutil
import subprocess
import json


def executable(name, override=None):
    override=override or os.environ.get("BIOPRINTER_"+name.upper().replace('-','_'))
    if override:
        if not Path(override).is_file(): raise ValueError(f"Executable override not found: {override}")
        return str(Path(override).resolve())
    registry=Path(__file__).resolve().parents[2]/'external-tools.local.json'
    if registry.is_file():
        item=json.loads(registry.read_text(encoding='utf-8')).get(name,{})
        if item.get('executable') and Path(item['executable']).is_file():
            return str(Path(item['executable']).resolve())
    aliases={"inkscape":["inkscape.com","inkscape"],"prusa-slicer":["prusa-slicer-console.exe","prusa-slicer","PrusaSlicer"]}
    for candidate in aliases.get(name,[name]):
        found=shutil.which(candidate)
        if found: return found
    for candidate in {"inkscape":["C:/Program Files/Inkscape/bin/inkscape.com","/Applications/Inkscape.app/Contents/MacOS/inkscape"],
        "prusa-slicer":["C:/Program Files/PrusaSlicer/prusa-slicer-console.exe","C:/Program Files/Prusa3D/PrusaSlicer/prusa-slicer-console.exe","/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer"]}.get(name,[]):
        if Path(candidate).is_file(): return candidate
    return None


def run(args, timeout=120):
    result=subprocess.run([str(a) for a in args],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout,shell=False)
    if result.returncode: raise ValueError(f"External command failed ({result.returncode}): {args[0]}\n{result.stdout}\n{result.stderr}")
    return result.stdout+result.stderr


def probe(name):
    exe=executable(name)
    if not exe: return {"available":False,"name":name}
    try:
        help_text=run([exe,"-h" if name in {"ffmpeg","ffprobe"} else "--help"],20)
        version=help_text if name=='prusa-slicer' else run([exe,"-version" if name in {"ffmpeg","ffprobe"} else "--version"],20)
        result={"available":True,"executable":exe,"version":version.splitlines()[0],"help":help_text}
        if name=="inkscape":
            result["actions"]=run([exe,"--action-list"],20)
            result["tracing"]=("object-trace available; adapter fixture verified on Windows 1.4.4"
                if 'object-trace' in result['actions'] else "manual round-trip; object-trace unavailable")
        return result
    except (ValueError,OSError,subprocess.TimeoutExpired) as exc:
        return {"available":False,"executable":exe,"error":str(exc)}


def doctor(profile):
    packages=["numpy","Pillow","opencv-python-headless","shapely","svgpathtools","pydantic","httpx","matplotlib","plotly"]
    return {"python":platform.python_version(),"platform":platform.platform(),
        "packages":{p:importlib.metadata.version(p) for p in packages},
        "external":{name:probe(name) for name in ("inkscape","prusa-slicer","ffmpeg","ffprobe")},
        "unresolved_production":profile.missing(True),"network_contacted":False}
