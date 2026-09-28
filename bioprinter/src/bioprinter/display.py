from pathlib import Path
import base64
import json


class LiveDisplay:
    """Approximate processed-byte display; never advances while paused/disconnected."""
    def __init__(self,timeline):
        self.timeline=timeline;self.event=None;self.observed=[]

    def update(self,status,observed_at,poll_latency_s=0):
        state=status.get('state');offset=status.get('file_position')
        if state=='processing' and offset is not None:
            eligible=[e for e in self.timeline['events'] if e['byte_start']<=offset]
            if eligible:self.event=eligible[-1]['event_id']
        record={'observed_at':observed_at,'state':state,'event_id':self.event,'file_position':offset,
                'poll_latency_s':poll_latency_s,'status':'approximate-buffered-file-position',
                'execution_latency_s':None}
        self.observed.append(record)
        return record


def write_player(run,timeline):
    run=Path(run);events=[]
    for e in timeline['events']:
        raw=(run/e['svg_path']).read_bytes()
        events.append({'start':e['start_s'],'end':e['end_s'],'name':e['event_id']+' · '+e['quadrant'],
                       'image':'data:image/svg+xml;base64,'+base64.b64encode(raw).decode()})
    # Local self-contained preview; no fetch, CDN or printer connection.
    payload=json.dumps(events).replace('</','<\\/')
    html='''<!doctype html><html><meta charset="utf-8"><title>Bioprinter display</title>
<style>body{background:#101a21;color:#eee;font:18px system-ui;margin:36px}img{background:white;width:70vw;height:65vh;object-fit:contain}button,input{font:inherit;margin:12px}input{width:60vw}</style>
<h1>Estimated display timeline</h1><p>Offline rehearsal. Timing does not track real printer pauses or firmware buffering.</p>
<img id="image"><h2 id="label"></h2><button id="play">Play</button><button id="pause">Pause</button><button id="reset">Reset</button><br><input id="seek" type="range" min="0" step="0.05"><span id="time"></span>
<script>const events=PAYLOAD;let t=0,playing=false,last=performance.now();const seek=document.getElementById('seek');seek.max=events.at(-1).end;
function draw(){const e=events.find(e=>t>=e.start&&t<e.end)||events.at(-1);document.getElementById('image').src=e.image;document.getElementById('label').textContent=e.name;seek.value=t;document.getElementById('time').textContent=t.toFixed(1)+' / '+Number(seek.max).toFixed(1)+' s'}
document.getElementById('play').onclick=()=>{playing=true;last=performance.now()};document.getElementById('pause').onclick=()=>playing=false;document.getElementById('reset').onclick=()=>{t=0;playing=false;draw()};seek.oninput=()=>{t=Number(seek.value);draw()};
function step(now){if(playing){t=Math.min(Number(seek.max),t+(now-last)/1000);if(t>=Number(seek.max))playing=false;draw()}last=now;requestAnimationFrame(step)}draw();requestAnimationFrame(step);</script></html>'''
    (run/'previews'/'display_player.html').write_text(html.replace('PAYLOAD',payload),encoding='utf-8')
