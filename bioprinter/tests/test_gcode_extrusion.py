import math
import pytest
from bioprinter.gcode import interpret,serialize,GCodeError,lex
from bioprinter.extrusion import convert_slicer,Reservoir


def test_modal_resets_relative_modes_inches():
    m,r=interpret('G21\nG90\nM82\nG1 X10 E5 F600\nG92 X0 E0\nG1 X2 E1\nG91\nM83\nG1 X3 E2\nG90\nG1 X0 E1\nG20\nG1 Y1 F60')
    assert m[1].end[0]==12
    assert m[2].end[0]==15
    assert m[3].end[0]==10 and m[3].e_delta==1
    assert m[-1].end[1]==pytest.approx(25.4)
    assert [v.e_delta for v in m[:4]]==[5,1,2,1]


@pytest.mark.parametrize('command',['M104 S0','M109 S50','M140 S0','M190 S0','M106 S0','M107','M141 S0','M191 S0','M116','M568 P0 S0','G10 P0 S0 R0','M307 H0 A0'])
def test_thermal_off_commands_removed(command):
    motions,report=interpret(command+'\nG1 X1 F60')
    assert len(motions)==1 and report[0]['action']=='removed'
    data,_,_=serialize(motions)
    assert lex(data.decode().splitlines()[-1])[0]=='G1'
    assert command not in data.decode()


@pytest.mark.parametrize('command',['G10','G10 P0 X1','G10 P0 X1 S0','G2 X1 I1','G3 X1 R1','M98 P1','T0','G28','G54','M302 P1','M500','M950 P0','G1 X{1} F60','N1 G1 X1*3','G1 X1 H2 F60','G1 X1 G1 Y2','G1 X1 X2'])
def test_unknown_motion_and_macros_reject(command):
    with pytest.raises(GCodeError) as exc:interpret(command)
    assert exc.value.report[-1]['action']=='rejected'


def test_comments_and_dwell():
    m,_=interpret('; M104 S100\nG1 X1 F60 (M106 S1)\nG4 P500\nG4 S2')
    assert [x.dwell for x in m]==[0,.5,2]
    with pytest.raises(GCodeError):interpret('G4 S-1')


def test_volume_direction_and_needle_independence(profile):
    motions,_=interpret('G1 X10 E2 F600\nG92 E0\nG1 X20 E3')
    a,r=convert_slicer(motions,profile)
    volume=5*math.pi*(1.75/2)**2
    assert sum(m.e_delta for m in a)*profile.mm3_per_e_unit==pytest.approx(volume)
    p=profile.model_copy(update={'needle_inner_diameter_mm':.2,'positive_extrusion_direction':-1})
    b,_=convert_slicer(motions,p)
    assert [m.e_delta for m in b]==pytest.approx([-m.e_delta for m in a])
    v=profile.model_copy(update={'slicer_e_mode':'mm3'})
    assert convert_slicer(motions,v)[1]['volume_mm3']==5


def test_capacity_survives_e_reset_and_retraction(profile):
    profile.capacity_mm3=2
    with pytest.raises(ValueError,match='capacity'):convert_slicer(interpret('G1 X10 E1 F100\nG92 E0\nG1 X20 E1')[0],profile)
    p=profile.model_copy(update={'capacity_mm3':100})
    m,r=convert_slicer(interpret('M83\nG1 E5 F60\nG1 E-5\nG1 X5 E1')[0],p)
    assert len(r['report'])==2 and len(m)==1
    reservoir=Reservoir(p,99)
    with pytest.raises(ValueError):reservoir.consume(2)


def test_final_policy_and_exact_bytes():
    m,_=interpret('G1 X10 F600\nG4 S1')
    raw,ranges,parsed=serialize(m)
    for r in ranges:
        assert raw[r['byte_start']:r['byte_end']]==raw.splitlines(keepends=True)[r['line']-1]
    with pytest.raises(GCodeError):interpret('M104 S0',final_policy=True)


def test_volumetric_inches_are_not_silently_scaled_as_length():
    with pytest.raises(GCodeError,match='Volumetric inch'):interpret('G20\nG1 X1 E1 F60',e_units='mm3')
