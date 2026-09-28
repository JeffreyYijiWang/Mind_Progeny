"""Explicit system-application installer. Standard-library only; dry plan by default.

Windows: WinGet official installer manifests and their SHA-256 validation.
macOS: Homebrew casks. Linux: existing distro manager or user Flatpak.
No installer is run by doctor, notebook, demo, imports or tests.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
URLS = {'inkscape': 'https://inkscape.org/release/',
        'prusa-slicer': 'https://github.com/prusa3d/PrusaSlicer/releases/latest'}
WIN_IDS = {'inkscape': 'Inkscape.Inkscape', 'prusa-slicer': 'Prusa3D.PrusaSlicer'}
FLATPAK_IDS = {'inkscape': 'org.inkscape.Inkscape', 'prusa-slicer': 'com.prusa3d.PrusaSlicer'}


def commands(tool, system=None, which=shutil.which, root=None):
    system = system or platform.system()
    if tool not in URLS:
        raise ValueError(f'Unknown application {tool}')
    if system == 'Windows':
        if not which('winget'):
            raise ValueError('Install Microsoft App Installer/WinGet first: https://aka.ms/getwinget; '
                             'or use the official installer at '+URLS[tool])
        return [[which('winget'), 'install', '--id', WIN_IDS[tool], '--exact', '--source', 'winget',
                 '--silent', '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity']]
    if system == 'Darwin':
        brew = which('brew')
        if not brew:
            for candidate in ('/opt/homebrew/bin/brew', '/usr/local/bin/brew'):
                if Path(candidate).is_file():
                    brew = candidate
                    break
        if not brew:
            raise ValueError('Install Homebrew from https://brew.sh first, or download the signed macOS app from '+URLS[tool])
        return [[brew, 'install', '--cask', 'inkscape' if tool=='inkscape' else 'prusaslicer']]
    if system != 'Linux':
        raise ValueError(f'Unsupported OS {system}; use {URLS[tool]}')
    # The current upstream Linux Prusa distribution is Flatpak; prefer it where available.
    if which('flatpak'):
        return [[which('flatpak'), 'remote-add', '--user', '--if-not-exists', 'flathub', 'https://flathub.org/repo/flathub.flatpakrepo'],
                [which('flatpak'), 'install', '--user', '--noninteractive', '-y', 'flathub', FLATPAK_IDS[tool]]]
    is_root = (os.geteuid()==0) if root is None else root
    prefix=[] if is_root else [which('sudo') or 'sudo']
    package='inkscape' if tool=='inkscape' else 'prusa-slicer'
    if which('apt-get'):
        return [prefix+[which('apt-get'),'update'], prefix+[which('apt-get'),'install','-y',package]]
    if which('dnf'):
        return [prefix+[which('dnf'),'install','-y',package]]
    if which('pacman'):
        return [prefix+[which('pacman'),'-S','--needed','--noconfirm',package]]
    if which('zypper'):
        return [prefix+[which('zypper'),'--non-interactive','install',package]]
    raise ValueError('No supported package manager. Install Flatpak, apt, dnf, pacman or zypper; see '+URLS[tool])


def discover(tool):
    env=os.environ.get('BIOPRINTER_'+tool.upper().replace('-','_'))
    if env and Path(env).is_file(): return str(Path(env).resolve())
    registry_path=ROOT/'external-tools.local.json'
    if registry_path.is_file():
        saved=json.loads(registry_path.read_text(encoding='utf-8')).get(tool,{}).get('executable')
        if saved and Path(saved).is_file(): return saved
    names={'inkscape':['inkscape.com','inkscape'],
           'prusa-slicer':['prusa-slicer-console.exe','prusa-slicer','PrusaSlicer']}[tool]
    for name in names:
        if shutil.which(name): return shutil.which(name)
    paths={'inkscape':['C:/Program Files/Inkscape/bin/inkscape.com', '/Applications/Inkscape.app/Contents/MacOS/inkscape'],
           'prusa-slicer':['C:/Program Files/PrusaSlicer/prusa-slicer-console.exe',
                          'C:/Program Files/Prusa3D/PrusaSlicer/prusa-slicer-console.exe',
                          '/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer']}[tool]
    for path in paths:
        if Path(path).is_file(): return str(Path(path).resolve())
    return None


def flatpak_launcher(tool, flatpak, root=ROOT):
    """A local executable bridge; per-invocation workspace/temp access, no global overrides."""
    folder=root/'.tools'/'launchers';folder.mkdir(parents=True,exist_ok=True)
    launcher=folder/tool
    argv=[flatpak,'run','--filesystem='+str(root.resolve()),'--filesystem=/tmp',FLATPAK_IDS[tool]]
    launcher.write_text('#!/bin/sh\nexec '+shlex.join(argv)+' "$@"\n',encoding='utf-8',newline='\n')
    launcher.chmod(0o755)
    return str(launcher.resolve())


def main(argv=None, default_tool=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tool',choices=['inkscape','prusa-slicer','both'],default=default_tool or 'both')
    parser.add_argument('--install',action='store_true',help='Explicitly download/install; otherwise print the plan only')
    parser.add_argument('--upgrade',action='store_true',help='Upgrade an existing detected Windows/macOS app')
    parser.add_argument('--report-dir',type=Path,default=ROOT/'validation'/'installations')
    args=parser.parse_args(argv)
    selected=list(URLS) if args.tool=='both' else [args.tool]
    report={'started_utc':datetime.now(timezone.utc).isoformat(),'system':platform.system(),
            'architecture':platform.machine(),'install_requested':args.install,'applications':{}}
    args.report_dir.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report_path=args.report_dir/(stamp+'.json')
    registry_path=ROOT/'external-tools.local.json'
    registry=json.loads(registry_path.read_text(encoding='utf-8')) if registry_path.exists() else {}
    failed=False
    for tool in selected:
        existing=discover(tool)
        info={'official_download_page':URLS[tool],'existing_executable':existing}
        report['applications'][tool]=info
        try:
            plan=commands(tool) if not existing or args.upgrade else []
            if args.upgrade:
                for command in plan:
                    if platform.system() in {'Windows','Darwin'}:
                        command[1]='upgrade'
            info['commands']=plan
            print(tool+': '+json.dumps(plan),flush=True)
            if args.install and (not existing or args.upgrade):
                info['logs']=[]
                for index,command in enumerate(plan):
                    log=args.report_dir/f'{stamp}_{tool}_{index}.log'
                    print('Installing '+tool+'; log: '+str(log),flush=True)
                    with log.open('wb') as stream:
                        result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=1800,shell=False)
                    info['logs'].append({'path':str(log),'returncode':result.returncode})
                    if result.returncode:
                        raise RuntimeError(f'Installer exited {result.returncode}; see {log}. No validation/hash bypass is used.')
            exe=discover(tool)
            if args.install and not exe and platform.system()=='Linux' and shutil.which('flatpak'):
                exe=flatpak_launcher(tool,shutil.which('flatpak'))
            info['executable']=exe
            if args.install and exe:
                # PrusaSlicer versions are probed via --help (not every release has --version).
                probe=subprocess.run([exe,'--version' if tool=='inkscape' else '--help'],capture_output=True,
                                     text=True,encoding='utf-8',errors='replace',timeout=30,shell=False)
                info['probe_returncode']=probe.returncode
                info['probe_output']=(probe.stdout+probe.stderr)
                if probe.returncode: raise RuntimeError('Installed executable failed its version/help probe')
                registry[tool]={'executable':exe,'installed_utc':datetime.now(timezone.utc).isoformat()}
                info['status']='verified-executable'
            elif args.install:
                raise RuntimeError('Installer returned success but executable was not discovered; supply BIOPRINTER override')
            else: info['status']='plan-only'
        except (ValueError,RuntimeError,OSError,subprocess.TimeoutExpired) as exc:
            failed=True;info['status']='failed';info['error']=str(exc);print(str(exc),file=sys.stderr,flush=True)
        report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    if args.install:
        registry_path.write_text(json.dumps(registry,indent=2),encoding='utf-8')
    print('Setup report: '+str(report_path),flush=True)
    return 1 if failed else 0


if __name__=='__main__': raise SystemExit(main())
