"""Explicit standalone-RRF network operations. No network work on import/construction."""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import os
import re
import time
import zlib
import httpx


class DuetError(RuntimeError): pass


def remote_path(name):
    if not re.fullmatch(r'/gcodes/bioprinter/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.gcode',name) or '..' in name:
        raise DuetError('Remote target must be a safe file inside /gcodes/bioprinter/<run>/')
    return name


class Duet:
    def __init__(self,base_url='http://hans.local',password=None,transport=None,timeout=10):
        url=httpx.URL(base_url)
        if url.scheme not in {'http','https'} or url.username or url.password or url.query or url.fragment:
            raise ValueError('Use an HTTP(S) base URL without credentials/query/fragment')
        self.base=str(url).rstrip('/');self.password=password if password is not None else os.environ.get('DUET_PASSWORD','reprap')
        self.client=httpx.Client(timeout=timeout,transport=transport,follow_redirects=False,trust_env=False)
        self.connected=False

    def close(self): self.client.close()

    def request(self,method,endpoint,*,safe=False,**kwargs):
        tries=3 if safe else 1
        for i in range(tries):
            try:
                response=self.client.request(method,self.base+'/'+endpoint,**kwargs)
                if response.status_code==503 and i+1<tries: time.sleep(.1);continue
                if response.status_code in {401,403}: raise DuetError('Duet authentication failed; check DUET_PASSWORD')
                if response.status_code==404:return response
                if response.status_code>=300:raise DuetError(f'Duet HTTP {response.status_code} at {endpoint}')
                return response
            except httpx.TransportError:
                if i+1==tries: raise DuetError(f'Duet connection failed during {endpoint}; mutation state may be ambiguous') from None
                time.sleep(.1)

    def connect(self):
        data=self.request('GET','rr_connect',params={'password':self.password,'sessionKey':'yes'}).json()
        if data.get('err')!=0: raise DuetError('Duet login rejected (password/session capacity)')
        if data.get('isEmulated'): raise DuetError('SBC/DSF API detected; this adapter targets standalone RRF')
        if 'sessionKey' in data:self.client.headers['X-Session-Key']=str(data['sessionKey'])
        self.connected=True

    def model(self,key):
        if not self.connected:self.connect()
        response=self.request('GET','rr_model',params={'key':key,'flags':'d99vn'},safe=True)
        if response.status_code==404: raise DuetError('RRF object-model API unavailable; use Duet Web Control/manual workflow')
        data=response.json()
        if 'result' not in data:raise DuetError('Invalid object-model response')
        return data['result']

    def status(self):
        start=time.monotonic();board=self.model('boards[0]');state=self.model('state');job=self.model('job');move=self.model('move')
        version=board.get('firmwareVersion')
        if not version or not version.startswith('3.'):raise DuetError('Only capability-checked standalone RRF 3.x is supported')
        return {'firmware_version':version,'state':state.get('status'),'current_tool':state.get('currentTool'),
            'file_name':(job.get('file') or {}).get('fileName'),'file_position':job.get('filePosition'),
            'last_file_name':job.get('lastFileName'),'last_duration_s':job.get('lastDuration'),
            'homed':{a.get('letter'):a.get('homed') for a in move.get('axes',[])},
            'position':{a.get('letter'):a.get('userPosition') for a in move.get('axes',[])},
            'poll_latency_s':time.monotonic()-start,'completion_evidence':'not-authoritative-on-standalone',
            'cold_extrusion_runtime_verified':False}

    def upload(self,run_dir,combined=True):
        from .pipeline import preflight
        root=Path(run_dir);profile,manifest=preflight(root,production=True)
        status=self.status()
        if status['firmware_version']!=profile.firmware_version:raise DuetError('Firmware differs from reviewed profile')
        if status['state']!='idle':raise DuetError('Upload requires idle machine')
        directories=['/gcodes/bioprinter','/gcodes/bioprinter/'+root.name]
        for directory in directories:
            # Existing directory is acceptable only if listing establishes it exists.
            listing=self.request('GET','rr_filelist',params={'dir':directory},safe=True)
            if listing.status_code==404 or listing.json().get('err'):
                if self.request('GET','rr_mkdir',params={'dir':directory}).json().get('err')!=0:
                    raise DuetError('Cannot create designated run directory')
        files=[root/'combined'/'combined.gcode'] if combined else sorted((root/'jobs').glob('*.gcode'))
        results=[]
        for path in files:
            target=remote_path(directories[-1]+'/'+path.name);content=path.read_bytes()
            existing=self.request('GET','rr_download',params={'name':target},safe=True)
            if existing.status_code!=404 and existing.content!=content:raise DuetError('Refusing to overwrite a different remote job')
            if existing.status_code==404:
                response=self.request('POST','rr_upload',params={'name':target,'crc32':f'{zlib.crc32(content):08x}'},content=content)
                if response.json().get('err')!=0:raise DuetError('Upload rejected')
            downloaded=self.request('GET','rr_download',params={'name':target},safe=True)
            if downloaded.status_code!=200 or downloaded.content!=content:raise DuetError('Remote byte verification failed')
            results.append({'path':target,'sha256':hashlib.sha256(content).hexdigest(),'verified':True})
        # Receipt is separate from immutable manifest. Upload never starts a job.
        (root/'upload.receipt.json').write_text(json.dumps({'base_url':self.base,'files':results},indent=2),encoding='utf-8')
        return results

    def _command_once(self,code):
        result=self.request('GET','rr_gcode',params={'gcode':code}).json()
        if 'buff' not in result or result.get('err',0):raise DuetError('Command was not acknowledged; reconcile machine state')

    def control(self,action,*,reviewed=False):
        if not reviewed:raise DuetError('Explicit --reviewed-macros required: pause/resume/cancel may invoke machine macros')
        mapping={'pause':'M25','resume':'M24','cancel':'M0'}
        if action not in mapping:raise ValueError('Unknown control')
        before=self.status();self._command_once(mapping[action]);after=self.status()
        return {'requested':action,'before':before,'after':after,'confirmed':after['state'] in {'paused','idle','processing'},
                'note':'Host control is not a physical emergency stop. Feedback can lag.'}


@contextmanager
def queue_lock(path):
    lock=Path(str(path)+'.lock')
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:raise DuetError('Queue already in use or stale lock; reconcile before removing lock') from None
    try:yield
    finally:os.close(fd);lock.unlink()


class Queue:
    def __init__(self,path,jobs=None):
        self.path=Path(path)
        if self.path.exists():self.state=json.loads(self.path.read_text(encoding='utf-8'))
        elif jobs is not None:
            self.state={'version':1,'index':0,'phase':'ready','seen_running':False,'jobs':jobs,'history':[]};self.save()
        else:raise DuetError('Queue state missing')

    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(self.state,indent=2),encoding='utf-8');os.replace(temp,self.path)

    def step(self,duet,*,start=False):
        with queue_lock(self.path):
            self.state=json.loads(self.path.read_text(encoding='utf-8'));s=self.state
            if s['index']>=len(s['jobs']):return 'complete'
            job=s['jobs'][s['index']]
            try:status=duet.status()
            except DuetError:
                if s['phase']!='ready':s['phase']='ambiguous';self.save()
                raise
            if status['state'] in {'halted','off','updating','cancelling'}:s['phase']='fault';self.save();return s['phase']
            expected=job['remote_path'].removeprefix('0:')
            actual=(status.get('file_name') or '').removeprefix('0:')
            if s['phase']=='ready':
                if not start:return 'ready'
                if status['state']!='idle':raise DuetError('Machine must be idle before queue start')
                if not all(status.get('homed',{}).get(axis) for axis in 'XYZ'):raise DuetError('XYZ must be homed by operator before starting')
                for axis,value in zip('XYZ',job['start_xyz']):
                    if status.get('position',{}).get(axis) is None or abs(status['position'][axis]-value)>.01:
                        raise DuetError('Machine pose does not match job precondition')
                # Check exact remote bytes immediately before sending the one-time start.
                remote=duet.request('GET','rr_download',params={'name':expected},safe=True)
                if remote.status_code!=200 or hashlib.sha256(remote.content).hexdigest()!=job['sha256']:
                    raise DuetError('Remote job missing or modified')
                s['phase']='start_intent';self.save()
                try:duet._command_once(f'M32 "0:{remote_path(expected)}"')
                except DuetError:s['phase']='ambiguous';self.save();raise
                s['phase']='starting';self.save();return 'starting'
            if s['phase'] in {'ambiguous','fault','awaiting_confirmation','start_intent'}:return s['phase']
            if status['state'] in {'processing','paused','pausing','resuming'}:
                if actual!=expected:s['phase']='ambiguous'
                else:s['seen_running']=True;s['phase']='running' if status['state']=='processing' else 'paused'
            elif status['state']=='idle':
                s['phase']='awaiting_confirmation' if s['seen_running'] else 'ambiguous'
            else:s['phase']='ambiguous'
            self.save();return s['phase']

    def confirm_completed(self,duet,job_id):
        with queue_lock(self.path):
            self.state=json.loads(self.path.read_text(encoding='utf-8'));s=self.state
            if s['index']>=len(s['jobs']):raise DuetError('Queue already complete')
            job=s['jobs'][s['index']]
            if s['phase'] not in {'awaiting_confirmation','ambiguous','fault','start_intent'} or job_id!=job['job_id']:
                raise DuetError('Exact current job and reconciliation phase required')
            status=duet.status()
            if status['state']!='idle':raise DuetError('Operator reconciliation requires idle machine')
            if (status.get('last_file_name') or '').removeprefix('0:')!=job['remote_path']:
                raise DuetError('Last-job identity does not match; retain queue for manual recovery')
            for axis,value in zip('XYZ',job['end_xyz']):
                if status.get('position',{}).get(axis) is None or abs(status['position'][axis]-value)>.01:
                    raise DuetError('End pose mismatch; do not resume continuation')
            s['history'].append({'job_id':job_id,'completion':'operator confirmed physical completion','observed':status})
            s['index']+=1;s['seen_running']=False;s['phase']='complete' if s['index']==len(s['jobs']) else 'ready';self.save()
            return s['phase']
