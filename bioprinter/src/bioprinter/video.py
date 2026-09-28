from pathlib import Path
import json
import math
import subprocess
from PIL import Image,ImageDraw
from .external import executable,run
from .geometry import read_svg,polygons
from .timing import validate_timeline


def render_svg(path,size=(640,480),background='white',policy='contain'):
    if policy not in {'contain','crop'}: raise ValueError('Image policy must be contain or crop')
    design=read_svg(path);g=design.geometry;x0,y0,x1,y1=g.bounds
    ratios=(size[0]/(x1-x0),size[1]/(y1-y0));scale=(min if policy=='contain' else max)(ratios)*.9
    image=Image.new('RGB',size,background);draw=ImageDraw.Draw(image)
    def coords(ring): return [((x-(x0+x1)/2)*scale+size[0]/2,((y0+y1)/2-y)*scale+size[1]/2) for x,y in ring.coords]
    for poly in polygons(g):
        draw.polygon(coords(poly.exterior),fill='#172b36')
        for hole in poly.interiors: draw.polygon(coords(hole),fill=background)
    return image


def create_video(run_dir,*,fps=24,size=(640,480),codec='libx264',quality=20,background='white',policy='contain',quadrants=False,timeline_path=None):
    root=Path(run_dir);tl=json.loads(Path(timeline_path or root/'timing'/'display_timeline.json').read_text(encoding='utf-8'));validate_timeline(tl)
    if fps<=0 or fps>120 or any(s<=0 or s%2 for s in size): raise ValueError('Positive fps<=120 and even dimensions required')
    if codec not in {'libx264','mpeg4'}: raise ValueError('Supported MOV codecs: libx264, mpeg4')
    ffmpeg=executable('ffmpeg');ffprobe=executable('ffprobe')
    if not ffmpeg or not ffprobe: raise ValueError('Optional video requires FFmpeg and ffprobe on PATH')
    if codec not in run([ffmpeg,'-hide_banner','-encoders']): raise ValueError(f'Installed FFmpeg lacks {codec}')
    output=root/'video'/'display.mov';output.parent.mkdir(parents=True,exist_ok=True)
    # Cumulative nearest frame boundaries avoid accumulated per-event rounding drift.
    boundaries=[0]+[math.floor(e['end_s']*fps+.5) for e in tl['events']]
    if any(b<=a for a,b in zip(boundaries,boundaries[1:])): raise ValueError('An event is shorter than one frame; raise fps')
    args=[ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pixel_format','rgb24',
          '-video_size',f'{size[0]}x{size[1]}','-framerate',str(fps),'-i','pipe:0','-an','-c:v',codec]
    args+=['-crf',str(quality)] if codec=='libx264' else ['-q:v',str(max(1,min(31,quality)))]
    args+=['-pix_fmt','yuv420p','-movflags','+faststart',str(output.resolve())]
    frames={};active={};log=output.with_suffix('.log')
    with log.open('wb') as stderr:
        proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=stderr,shell=False)
        try:
            for i,event in enumerate(tl['events']):
                path=(root/event['svg_path']).resolve()
                if not path.is_relative_to(root.resolve()): raise ValueError('Timeline asset outside run')
                key=str(path)
                if key not in frames: frames[key]=render_svg(path,size,background,policy)
                frame=frames[key]
                if quadrants:
                    active[event['quadrant']]=frame
                    frame=Image.new('RGB',size,background);draw=ImageDraw.Draw(frame)
                    for q,(x,y) in {'Q1':(size[0]//2,0),'Q2':(size[0]//2,size[1]//2),'Q3':(0,size[1]//2),'Q4':(0,0)}.items():
                        if q in active: frame.paste(active[q].resize((size[0]//2,size[1]//2)),(x,y))
                        if q==event['quadrant']:draw.rectangle((x,y,x+size[0]//2-1,y+size[1]//2-1),outline='red',width=3)
                raw=frame.tobytes()
                for _ in range(boundaries[i+1]-boundaries[i]): proc.stdin.write(raw)
            proc.stdin.close();proc.wait(timeout=120)
        except BaseException:
            proc.kill();proc.wait();raise
    if proc.returncode: raise ValueError('FFmpeg failed; inspect '+str(log))
    measured=float(json.loads(run([ffprobe,'-v','error','-show_entries','format=duration','-of','json',str(output)]))['format']['duration'])
    expected=tl['timing']['total_s'];tolerance=1/fps+.001
    if abs(measured-expected)>tolerance: raise ValueError(f'MOV duration {measured} differs from {expected} by more than {tolerance}')
    report={'duration_s':measured,'timeline_s':expected,'difference_s':measured-expected,'tolerance_s':tolerance,
            'fps':fps,'frames':boundaries[-1],'codec':codec,'argv':args,'timeline_status':tl['timing']['status'],
            'synchronization':'Estimated schedule; printer pauses are not encoded'}
    output.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
