import hashlib
import json
from pathlib import Path
import httpx
import pytest
from bioprinter.duet import Duet,Queue,DuetError,remote_path
from bioprinter.external import executable
from fake_duet import FakeDuet


def setup_queue(tmp_path):
    fake=FakeDuet();client=Duet('http://fake.invalid',transport=httpx.MockTransport(fake.handler))
    raw=b'G21\nG90\nM83\nG1 X10 Y10 Z3 F60\n';name='/gcodes/bioprinter/run/one.gcode';fake.files[name]=raw
    job={'job_id':'one','remote_path':name,'sha256':hashlib.sha256(raw).hexdigest(),'start_xyz':[0,0,2],'end_xyz':[10,10,3]}
    queue=Queue(tmp_path/'queue.json',[job,{**job,'job_id':'two','start_xyz':[10,10,3]}])
    return fake,client,queue


def test_status_readonly_auth_and_disconnect(tmp_path):
    f,c,q=setup_queue(tmp_path)
    assert c.status()['firmware_version']=='3.5.4' and not f.commands
    f.disconnect=True
    with pytest.raises(DuetError,match='connection'):c.status()
    f.disconnect=False;f.fail_auth=True
    with pytest.raises(DuetError,match='login'):c.connect()


def test_queue_complete_requires_operator_and_no_duplicate_start(tmp_path):
    f,c,q=setup_queue(tmp_path)
    assert q.step(c)=='ready' and not f.commands
    assert q.step(c,start=True)=='starting'
    assert q.step(c,start=True)=='running' and len(f.commands)==1
    f.finish()
    assert q.step(c,start=True)=='awaiting_confirmation' and len(f.commands)==1
    assert q.step(c,start=True)=='awaiting_confirmation'
    assert q.confirm_completed(c,'one')=='ready'
    assert q.step(c,start=True)=='starting' and len(f.commands)==2


def test_cancel_not_success_and_ambiguous_restart(tmp_path):
    f,c,q=setup_queue(tmp_path);q.step(c,start=True);q.step(c)
    c.control('cancel',reviewed=True)
    assert q.step(c,start=True)=='awaiting_confirmation'
    # Cancelled at a different position cannot become a completed continuation.
    with pytest.raises(DuetError,match='pose'):q.confirm_completed(c,'one')
    f.disconnect=True
    with pytest.raises(DuetError):q.step(c,start=True)
    f.disconnect=False
    reopened=Queue(q.path)
    assert reopened.step(c,start=True)=='ambiguous' and len(f.commands)==2


def test_lost_start_response_never_retries(tmp_path):
    f,c,q=setup_queue(tmp_path);f.disconnect_after_start=True
    with pytest.raises(DuetError):q.step(c,start=True)
    assert len(f.commands)==1
    assert Queue(q.path).step(c,start=True)=='ambiguous' and len(f.commands)==1


def test_fault_unhomed_and_unsafe_remote_paths(tmp_path):
    f,c,q=setup_queue(tmp_path);f.homed=False
    with pytest.raises(DuetError,match='homed'):q.step(c,start=True)
    f.state='halted';assert q.step(c)=='fault'
    for name in ['/sys/config.g','/gcodes/bioprinter/../../sys/config.g','/gcodes/bioprinter/x/a".gcode']:
        with pytest.raises(DuetError):remote_path(name)


def test_upload_exact_bytes_no_start(tmp_path,monkeypatch,profile):
    f,c,q=setup_queue(tmp_path);root=tmp_path/'run001';(root/'combined').mkdir(parents=True)
    raw=b'G21\nG90\nM83\nG1 X0 Y0 Z3 F60\n';(root/'combined'/'combined.gcode').write_bytes(raw)
    profile.firmware_version='3.5.4'
    monkeypatch.setattr('bioprinter.pipeline.preflight',lambda *a,**k:(profile,{}))
    result=c.upload(root)
    assert result[0]['verified'] and f.files[result[0]['path']]==raw and not f.commands
    count=sum(method=='POST' for method,path in f.requests)
    c.upload(root)
    assert sum(method=='POST' for method,path in f.requests)==count


@pytest.mark.external
def test_video_duration_cumulative_rounding(tmp_path):
    if not executable('ffmpeg') or not executable('ffprobe'):pytest.skip('FFmpeg/ffprobe unavailable')
    from bioprinter.video import create_video
    root=tmp_path/'movie with spaces ä';(root/'timing').mkdir(parents=True)
    svg=root/'image.svg';svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>')
    intervals=[.36,.73,1.07];events=[];start=0
    for n,end in enumerate(intervals):
        events.append({'event_id':str(n),'svg_path':'image.svg','quadrant':'Q1','start_s':start,'end_s':end,'duration_s':end-start,'byte_start':n,'byte_end':n+1});start=end
    (root/'timing'/'display_timeline.json').write_text(json.dumps({'events':events,'timing':{'total_s':1.07,'status':'estimated'}}))
    report=create_video(root,fps=10,size=(160,120))
    assert report['frames']==11 and report['duration_s']==pytest.approx(1.1,abs=.001)
    assert abs(report['difference_s'])<=report['tolerance_s']
