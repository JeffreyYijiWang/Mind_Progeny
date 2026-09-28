import importlib.util
from pathlib import Path
import zipfile
import pytest
from bioprinter.archive import extract_images

spec=importlib.util.spec_from_file_location('setup_external',Path(__file__).resolve().parents[1]/'scripts'/'setup_external.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)


@pytest.mark.parametrize('tool,package',[('inkscape','Inkscape.Inkscape'),('prusa-slicer','Prusa3D.PrusaSlicer')])
def test_windows_installer_plan(tool,package):
    plan=setup.commands(tool,'Windows',lambda p:'C:/WindowsApps/winget.exe' if p=='winget' else None)
    assert plan[0][plan[0].index('--id')+1]==package
    assert '--silent' in plan[0] and '--ignore-security-hash' not in plan[0]


@pytest.mark.parametrize('tool,cask',[('inkscape','inkscape'),('prusa-slicer','prusaslicer')])
def test_mac_installer_plan(tool,cask):
    assert setup.commands(tool,'Darwin',lambda p:'/opt/homebrew/bin/brew' if p=='brew' else None)==[['/opt/homebrew/bin/brew','install','--cask',cask]]


@pytest.mark.parametrize('manager',['apt-get','dnf','pacman','zypper'])
def test_linux_package_plan(manager):
    plan=setup.commands('prusa-slicer','Linux',lambda p:'/usr/bin/'+p if p in {manager,'sudo'} else None,root=False)
    assert plan[-1][0]=='/usr/bin/sudo' and 'prusa-slicer' in plan[-1]


def test_linux_flatpak_user_install():
    plan=setup.commands('prusa-slicer','Linux',lambda p:'/usr/bin/flatpak' if p=='flatpak' else None,root=False)
    assert all('--user' in p for p in plan) and 'com.prusa3d.PrusaSlicer' in plan[-1]


def test_flatpak_launcher_quotes_workspace(tmp_path):
    script=Path(setup.flatpak_launcher('inkscape','/usr/bin/flatpak',tmp_path/'space and quote\' folder'))
    import shlex
    argv=shlex.split(script.read_text().splitlines()[1])
    assert argv[-2:]==['org.inkscape.Inkscape','$@']
    assert '--filesystem='+str(script.parents[2].resolve()) in argv
    assert '--filesystem=/tmp' in argv


@pytest.mark.parametrize('member',['../escape.png','C:/escape.png','dir\\escape.png','CON.png','dir /image.png'])
def test_archive_paths_fail_before_writing(tmp_path,member):
    archive=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr(member.replace('\\','/'),b'image')
    # ZipFile normalizes separators on Windows; patch both filename headers to test
    # the actual untrusted backslash input rather than its harmless normalized form.
    if '\\' in member:
        archive.write_bytes(archive.read_bytes().replace(member.replace('\\','/').encode(),member.encode()))
    with pytest.raises(ValueError,match='Unsafe'):extract_images(archive,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_archive_hashes_count_and_unicode(tmp_path):
    archive=tmp_path/'images.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('DATA SET/test\u202fphoto.png',b'fixture bytes')
    meta=extract_images(archive,tmp_path/'out',expected_count=1)
    assert meta['image_count']==1 and len(meta['images'][0]['sha256'])==64
    assert (tmp_path/'out'/'DATA SET'/'test\u202fphoto.png').read_bytes()==b'fixture bytes'


def test_setup_default_cannot_install(tmp_path,monkeypatch):
    monkeypatch.setattr(setup,'ROOT',tmp_path)
    monkeypatch.setattr(setup,'discover',lambda tool:None)
    monkeypatch.setattr(setup,'commands',lambda tool:[['fixture-manager','install',tool]])
    def forbidden(*args,**kwargs): raise AssertionError('Plan mode must not execute subprocesses')
    monkeypatch.setattr(setup.subprocess,'run',forbidden)
    assert setup.main(['--report-dir',str(tmp_path/'reports')])==0
    assert not (tmp_path/'external-tools.local.json').exists()
