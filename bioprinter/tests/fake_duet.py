import httpx


class FakeDuet:
    """HTTP transport fixture, never a claim about hardware behavior."""
    def __init__(self):
        self.state='idle';self.current=None;self.last=None;self.position=[0,0,2]
        self.files={};self.commands=[];self.fail_auth=False;self.disconnect=False;self.disconnect_after_start=False
        self.requests=[];self.dirs={'/gcodes/bioprinter'};self.firmware='3.5.4';self.homed=True

    def handler(self,request):
        self.requests.append((request.method,request.url.path))
        if self.disconnect:raise httpx.ConnectError('offline',request=request)
        path=request.url.path;p=request.url.params
        if path=='/rr_connect':return httpx.Response(200,json={'err':1 if self.fail_auth else 0,'sessionKey':123})
        if path=='/rr_model':
            data={'boards[0]':{'firmwareVersion':self.firmware},'state':{'status':self.state,'currentTool':0},
                'job':{'file':{'fileName':self.current},'filePosition':123,'lastFileName':self.last,'lastDuration':10},
                'move':{'axes':[{'letter':a,'homed':self.homed,'userPosition':v} for a,v in zip('XYZ',self.position)]}}
            return httpx.Response(200,json={'result':data[p['key']]})
        if path=='/rr_download':return httpx.Response(200,content=self.files[p['name']]) if p['name'] in self.files else httpx.Response(404)
        if path=='/rr_filelist':return httpx.Response(200,json={'err':0 if p['dir'] in self.dirs else 1,'files':[]})
        if path=='/rr_mkdir':self.dirs.add(p['dir']);return httpx.Response(200,json={'err':0})
        if path=='/rr_upload':self.files[p['name']]=request.content;return httpx.Response(200,json={'err':0})
        if path=='/rr_gcode':
            code=p['gcode'];self.commands.append(code)
            if code.startswith('M32'):
                self.current=code.split('"')[1];self.state='processing'
                if self.disconnect_after_start:raise httpx.ReadError('response lost',request=request)
            elif code=='M25':self.state='paused'
            elif code=='M24':self.state='processing'
            elif code=='M0':self.last=self.current;self.current=None;self.state='idle'
            return httpx.Response(200,json={'buff':1024})
        return httpx.Response(404)

    def finish(self,xyz=(10,10,3)):
        self.last=self.current;self.current=None;self.state='idle';self.position=list(xyz)
