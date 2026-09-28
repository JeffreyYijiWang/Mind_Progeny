import json
import math
import numpy as np
import pytest
from shapely.geometry import box
from bioprinter.config import Profile
from bioprinter.layout import schedule,placement
from bioprinter.slicing import Toolpath
from bioprinter.stacking import Planner,HeightField,CollisionError
from bioprinter.gcode import Motion
from bioprinter.timing import duration,estimate
from bioprinter.display import LiveDisplay


def event(index=0):return {'event_id':str(index),'quadrant':'Q1','nominal_layer_index':index,'asset_id':'fixture'}


def test_real_profile_fails_and_confirmed_fields_independent():
    p=Profile();assert p.needle_gauge==23 and p.needle_length_mm==12.7
    assert p.needle_gauge_confirmed and p.needle_length_confirmed
    assert 'confirm:positive_extrusion_direction' in p.missing(True)
    assert 'confirm:spread_factor' in p.missing(True)
    with pytest.raises(ValueError,match='Unresolved'):p.require(True)


def test_schedule_skips_and_oversized(profile):
    seq={'Q1':['a','b'],'Q2':[],'Q3':['c'],'Q4':['d']}
    assert [q for q,i,a in schedule(seq)]==['Q1','Q3','Q4','Q1']
    assert [q for q,i,a in schedule(seq,'complete_stack')]==['Q1','Q1','Q3','Q4']
    with pytest.raises(ValueError,match='do not fit'):placement((0,0,110,20),'Q1',profile)


def test_overlap_is_local_and_footprints_not_rectangle(profile):
    planner=Planner(profile);allowed=box(0,0,60,125)
    planner.add([Toolpath([(10,10),(20,10)],.5)],event(),allowed)
    planner.add([Toolpath([(15,10),(25,10)],.5)],event(1),allowed)
    field=planner.field
    assert field.maximum((17,10),(17,10),.01)==pytest.approx(1)
    assert field.maximum((23,10),(23,10),.01)==pytest.approx(.5)
    assert field.maximum((17,14),(17,14),.01)==0
    deposition=[m for m in planner.plan.motions if m.e_delta and m.event=='1']
    assert max(m.end[2] for m in deposition)>min(m.end[2] for m in deposition)
    assert all(m.start[2]==m.end[2] for m in deposition)
    assert planner.plan.used_mm3==pytest.approx(10)
    assert all(min(m.start[2],m.end[2])>=1+profile.travel_clearance_mm for m in planner.plan.motions
               if m.event=='1' and not m.e_delta and m.start[:2]!=m.end[:2] and max(m.start[2],m.end[2])>=3)


def test_holder_valley_needle_and_z_collision(profile):
    field=HeightField(profile)
    sl,mask=field.cells((10,10),(10,10),.1);field.z[sl][mask]=20
    with pytest.raises(CollisionError,match='Needle'):field.check_pose((10,10),(10,10),1)
    with pytest.raises(CollisionError,match='Holder'):field.check_pose((11.5,10),(11.5,10),1)
    with pytest.raises(CollisionError,match='Z'):field.check_pose((0,0),(0,0),101)
    with pytest.raises(CollisionError,match='XY'):field.check_pose((profile.x_max,0),(profile.x_max,0),30)


def test_kinematics_independently_known(profile):
    p=profile.model_copy(update={'xy_speed_mm_s':10,'xy_accel_mm_s2':100,'e_speed_units_s':1,'e_accel_units_s2':10,'z_speed_mm_s':2,'z_accel_mm_s2':4})
    x=Motion((0,0,0),(10,0,0),feed=600)
    e=Motion((0,0,0),(0,0,0),e_delta=1,feed=60)
    z=Motion((0,0,0),(0,0,1),feed=120)
    dwell=Motion((0,0,1),(0,0,1),dwell=2)
    assert duration(x,p)==pytest.approx(1.1) # 0.1 accel +0.9 cruise +0.1 decel
    assert duration(e,p)==pytest.approx(1.1)
    assert duration(z,p)==pytest.approx(1) # triangular sqrt(1/4)*2
    assert estimate([x,e,z,dwell],p)['total_s']==pytest.approx(5.2)
    simultaneous=Motion((0,0,0),(10,0,0),e_delta=10,feed=600)
    assert duration(simultaneous,p)==pytest.approx(10.1)


def test_emitted_feed_enforces_syringe_rate(profile):
    profile.e_speed_units_s=.001
    planner=Planner(profile)
    planner.add([Toolpath([(10,10),(12,10)],.5)],event(),box(0,0,60,125))
    for m in planner.plan.motions:
        if m.e_delta:
            seconds=m.length/(m.feed/60)
            assert abs(m.e_delta)/seconds<=profile.e_speed_units_s+1e-10


def test_complete_demo_provenance_timeline_no_repeated_startup(demo_run):
    from bioprinter.pipeline import preflight
    p,manifest=preflight(demo_run,production=False)
    assert len(manifest['assets'])==3 and len(manifest['events'])==12
    assert manifest['network_contacted'] is False
    data=(demo_run/'combined'/'combined.gcode').read_bytes()
    assert data.count(b'G21\n')==1 and b'G28' not in data and b'G92' not in data
    tl=json.loads((demo_run/'timing'/'display_timeline.json').read_text())
    for e in tl['events']:
        assert data[e['byte_start']:e['byte_end']]==b''.join(data.splitlines(keepends=True)[e['line_start']-1:e['line_end']])
    jobs=json.loads((demo_run/'timing'/'jobs.json').read_text())['jobs']
    assert jobs[0]['type']=='standalone' and all(j['type']=='continuation' for j in jobs[1:])
    for a,b in zip(jobs,jobs[1:]):
        assert b['start_xyz']==a['end_xyz'] and b['used_before_mm3']==a['used_after_mm3']
    player=LiveDisplay(tl)
    first=player.update({'state':'processing','file_position':tl['events'][0]['byte_start']},10)
    paused=player.update({'state':'paused','file_position':tl['events'][-1]['byte_end']},20)
    assert paused['event_id']==first['event_id']
    assert player.update({'state':'disconnected'},30)['event_id']==first['event_id']
    with pytest.raises(ValueError,match='synthetic'):preflight(demo_run,production=True)


def test_changed_bytes_rejected(demo_run,tmp_path):
    import shutil
    from bioprinter.pipeline import preflight
    copy=tmp_path/'tamper';shutil.copytree(demo_run,copy)
    (copy/'combined'/'combined.gcode').write_bytes(b'G28\n')
    with pytest.raises(ValueError,match='changed'):preflight(copy,production=False)
