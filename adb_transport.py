import os,socket,sys,struct,time
from pathlib import Path

def exact(s,n):
    out=b''
    while len(out)<n:
        part=s.recv(n-len(out))
        if not part:raise EOFError()
        out+=part
    return out
def request(s,q):
    q=q.encode();s.sendall(f'{len(q):04x}'.encode()+q)
    status=exact(s,4)
    if status!=b'OKAY':raise RuntimeError(exact(s,int(exact(s,4),16)))
SERIAL=os.environ.get('ANDROID_SERIAL')

def select(s):
    if not SERIAL:raise ValueError('ADB serial is required; use --serial or set ANDROID_SERIAL')
    request(s,'host:transport:'+SERIAL)

def shell(cmd,timeout=20):
    with socket.create_connection(('127.0.0.1',5037),timeout=timeout) as s:
        select(s)
        request(s,'shell:'+cmd)
        out=[]
        while True:
            x=s.recv(65536)
            if not x:break
            out.append(x)
        return b''.join(out)
def pull(remote,local):
    with socket.create_connection(('127.0.0.1',5037),timeout=30) as s:
        select(s);request(s,'sync:')
        p=remote.encode();s.sendall(b'RECV'+struct.pack('<I',len(p))+p)
        with Path(local).open('wb') as f:
            while True:
                tag=exact(s,4);n=struct.unpack('<I',exact(s,4))[0]
                if tag==b'DONE':break
                if tag!=b'DATA':raise RuntimeError(tag+exact(s,n))
                f.write(exact(s,n))
def push(local,remote,mode=0o644):
    with socket.create_connection(('127.0.0.1',5037),timeout=120) as s:
        select(s);request(s,'sync:')
        p=(remote+','+str(0o100000|mode)).encode();s.sendall(b'SEND'+struct.pack('<I',len(p))+p)
        with Path(local).open('rb') as f:
            while b:=f.read(65536):s.sendall(b'DATA'+struct.pack('<I',len(b))+b)
        s.sendall(b'DONE'+struct.pack('<I',int(time.time())))
        tag=exact(s,4);n=struct.unpack('<I',exact(s,4))[0]
        if tag!=b'OKAY':raise RuntimeError(tag+exact(s,n))
if __name__=='__main__':
    cmd=sys.argv[1]
    out=shell(cmd)
    if len(sys.argv)>2:Path(sys.argv[2]).write_bytes(out)
    print(out.decode('utf8','replace'))
