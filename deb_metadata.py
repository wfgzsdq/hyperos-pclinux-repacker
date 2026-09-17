"""Read Debian metadata and desktop integration without extracting package paths."""
import configparser,hashlib,io,json,posixpath,re,shlex,struct,tarfile
from pathlib import Path
from repack import ar_members,clean_name,open_tar

def fields(text):
    result={};last=None
    for line in text.splitlines():
        if line.startswith((' ','\t')) and last:result[last]+='\n'+line.strip()
        elif ':' in line:last,value=line.split(':',1);result[last]=value.strip()
    return result

def desktop_fields(text):
    parser=configparser.ConfigParser(interpolation=None,strict=False)
    parser.optionxform=str;parser.read_string(text)
    return dict(parser['Desktop Entry']) if parser.has_section('Desktop Entry') else {}

class Deb:
    def __init__(self,path):
        self.path=Path(path);self.metadata={};self.payload=None
        with self.path.open('rb') as f:self.sha256=hashlib.file_digest(f,'sha256').hexdigest()
        for name,data in ar_members(self.path):
            if name.startswith('control.tar'):
                with open_tar(data) as t:
                    for m in t:
                        if clean_name(m.name)=='control':self.metadata=fields(t.extractfile(m).read().decode('utf8'))
            elif name.startswith('data.tar'):self.payload=data
        if not self.metadata or self.payload is None:raise ValueError('Missing deb control/data archive')
        if self.metadata.get('Architecture')!='arm64':raise ValueError('Main package must declare Architecture: arm64')
        self.tar=open_tar(self.payload);self.members={};self.desktops={}
        for m in self.tar:
            name=clean_name(m.name)
            if name in self.members:raise ValueError('Duplicate tar path: '+name)
            self.members[name]=m
            if name.startswith('usr/share/applications/') and name.endswith('.desktop') and m.isfile():
                self.desktops[name]=desktop_fields(self.tar.extractfile(m).read().decode('utf8'))

    def close(self):self.tar.close();self.payload=None

    def resolve(self,name):
        name=clean_name(name.lstrip('/'));seen=set()
        for _ in range(32):
            if name in seen:raise ValueError('Cyclic package symlink: '+name)
            seen.add(name);m=self.members.get(name)
            if m is None:raise ValueError('Path not present in deb: '+name)
            if m.issym():
                name=posixpath.normpath(m.linkname.lstrip('/') if m.linkname.startswith('/') else posixpath.join(posixpath.dirname(name),m.linkname))
                name=clean_name(name)
            elif m.islnk():name=clean_name(m.linkname)
            else:return name,m
        raise ValueError('Too many symlink hops')

    def executable(self,value):
        candidates=[value.lstrip('/')] if '/' in value else [value,'usr/bin/'+value,'bin/'+value,'usr/local/bin/'+value]
        for candidate in candidates:
            if candidate in self.members:
                name,m=self.resolve(candidate)
                if not m.isfile() or not m.mode&0o111:raise ValueError('Not an executable regular file: '+name)
                return name
        raise ValueError('Cannot locate Exec executable in package; supply --entry: '+value)

    def select_desktop(self,name=None):
        if name:
            candidates=[p for p in self.desktops if p==name.lstrip('/') or posixpath.basename(p)==name]
        else:candidates=[p for p,d in self.desktops.items() if d.get('Type')=='Application' and d.get('NoDisplay','false').lower()!='true' and d.get('Hidden','false').lower()!='true' and d.get('Exec')]
        if len(candidates)!=1:raise ValueError('Choose --desktop (or --entry for packages without a desktop launcher): '+', '.join(candidates or self.desktops))
        return candidates[0],self.desktops[candidates[0]]

    def command(self,path,d):
        words=shlex.split(d.get('Exec',''))
        if not words:raise ValueError('Desktop entry has no Exec; use --entry')
        if words[0]=='env' or words[0].endswith('/env'):raise ValueError('Exec uses env; supply --entry and configure env explicitly')
        entry=self.executable(words[0]);args=[]
        for w in words[1:]:
            if w in ('%f','%F','%u','%U','%i','%d','%D','%n','%N','%v','%m'):continue
            w=w.replace('%%','\x00').replace('%c',d.get('Name','')).replace('%k','@APP@/'+path)
            if re.search(r'%[A-Za-z]',w):raise ValueError('Unsupported desktop field code: '+w)
            args.append(w.replace('\x00','%'))
        return entry,args

    def icon(self,d,output,override=None,member=None):
        icon=d.get('Icon','');candidates=[]
        if override:
            raw=Path(override).read_bytes();source=str(Path(override).resolve())
        elif member:
            source,rm=self.resolve(member)
            if not rm.isfile() or rm.size>16*1024*1024:raise ValueError('Configured icon member is not a usable file: '+member)
            raw=self.tar.extractfile(rm).read()
        else:
            for name,m in self.members.items():
                if not (m.isfile() or m.issym()) or not name.lower().endswith('.png'):continue
                match=(name==icon.lstrip('/') or posixpath.basename(name)==icon or posixpath.basename(name)==icon+'.png')
                if match:
                    resolved,rm=self.resolve(name)
                    if rm.isfile() and rm.size<=16*1024*1024:
                        data=self.tar.extractfile(rm).read()
                        if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data)>=24:
                            w,h=struct.unpack('>II',data[16:24]);candidates.append((min(w,h),name,data))
            if not candidates:return None
            _,source,raw=max(candidates,key=lambda c:(c[0],c[1]))
        if not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw)<24:raise ValueError('--icon must be a PNG file')
        w,h=struct.unpack('>II',raw[16:24])
        if not (1<=w<=4096 and 1<=h<=4096):raise ValueError('Icon dimensions must be 1..4096')
        output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(raw)
        return {'source':source,'sha256':hashlib.sha256(raw).hexdigest(),'width':w,'height':h,'path':str(output.resolve())}

    def inspect(self):
        return {'source_type':'deb','source':str(self.path.resolve()),'sha256':self.sha256,'metadata':self.metadata,'desktop_entries':self.desktops,'files':len(self.members)}
