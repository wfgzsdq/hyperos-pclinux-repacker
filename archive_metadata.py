"""Inspect and normalize relocatable tar distributions without extracting them."""
import copy,gzip,hashlib,json,posixpath,re,struct,tarfile
from pathlib import Path
from deb_metadata import Deb,desktop_fields
from repack import clean_name

def stripped_name(name,count):
    name=clean_name(name)
    parts=[] if name=='.' else name.split('/')
    if len(parts)<=count:return None
    return '/'.join(parts[count:])

def layout(path,strip_components=None):
    with tarfile.open(path,'r:*') as tar:members=tar.getmembers()
    if not members:raise ValueError('Archive is empty')
    names=[clean_name(m.name) for m in members if clean_name(m.name)!='.']
    if strip_components is None:
        first={n.split('/')[0] for n in names}
        roots={clean_name(m.name) for m in members if m.isdir() and '/' not in clean_name(m.name)}
        strip_components=1 if len(first)==1 and first.issubset(roots) and any('/' in n for n in names) else 0
    if type(strip_components) is not int or not 0<=strip_components<=8:raise ValueError('archive_strip_components must be an integer from 0 to 8')
    mapped={};original={}
    for m in members:
        name=stripped_name(m.name,strip_components)
        if name is None:continue
        if name in mapped:raise ValueError('Duplicate path after stripping archive prefix: '+name)
        if not (m.isfile() or m.isdir() or m.issym() or m.islnk()):raise ValueError('Special archive member rejected: '+m.name)
        mapped[name]=m;original[name]=clean_name(m.name)
    if not mapped:raise ValueError('archive_strip_components removed every member')
    return strip_components,mapped,original

def scan_elf(path,strip_components):
    machines={};incompatible=[]
    with tarfile.open(path,'r|*') as tar:
        for m in tar:
            name=stripped_name(m.name,strip_components)
            if name is None or not m.isfile() or not (m.mode&0o111):continue
            f=tar.extractfile(m);head=f.read(64) if f else b''
            if head[:4]!=b'\x7fELF':continue
            if len(head)<20:raise ValueError('Truncated ELF header: '+name)
            machine=struct.unpack_from('<H' if head[5]==1 else '>H',head,18)[0]
            machines[name]=machine
            if head[4:6]!=b'\x02\x01' or machine!=183:incompatible.append(name)
    if incompatible:raise ValueError('Non-ARM64 executable ELF files in archive: '+', '.join(incompatible[:12]))
    return machines

class Archive(Deb):
    def __init__(self,path,strip_components=None):
        self.path=Path(path)
        with self.path.open('rb') as f:self.sha256=hashlib.file_digest(f,'sha256').hexdigest()
        self.strip_components,self.members,self.original_names=layout(self.path,strip_components)
        self.tar=tarfile.open(self.path,'r:*');self.payload=None;self.desktops={}
        for name,m in self.members.items():
            if name.lower().endswith('.desktop') and m.isfile() and m.size<=1024*1024:
                self.desktops[name]=desktop_fields(self.tar.extractfile(m).read().decode('utf8'))
        base=re.sub(r'(?i)(?:\.tar)?\.(?:xz|gz|bz2|zst)$','',self.path.name)
        base=re.sub(r'(?i)[_-](?:linux[-_])?(?:aarch64|arm64).*$','',base)
        package=re.sub('[^a-z0-9]+','-',base.lower()).strip('-') or 'application'
        version='unknown'
        for name,m in self.members.items():
            if posixpath.basename(name)=='application.ini' and m.isfile() and m.size<1024*1024:
                text=self.tar.extractfile(m).read().decode('utf8','replace')
                found=re.search(r'^Version=(.+)$',text,re.M)
                if found:version=found.group(1).strip();break
        self.metadata={'Package':package,'Version':version,'Architecture':'arm64','Depends':'not declared by archive'}
        self.elf_machines=scan_elf(self.path,self.strip_components)

    def icon(self,d,output,override=None,member=None):
        result=super().icon(d,output,override,member)
        if result:return result
        candidates=[]
        for name,m in self.members.items():
            if not m.isfile() or not re.search(r'(?i)(?:^|/)icons?/icon(?:[_-]?\d+)?\.png$',name) or m.size>16*1024*1024:continue
            data=self.tar.extractfile(m).read()
            if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data)>=24:
                w,h=struct.unpack('>II',data[16:24]);candidates.append((min(w,h),name,data,w,h))
        if not candidates:return None
        _,source,raw,w,h=max(candidates,key=lambda x:(x[0],x[1]))
        output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(raw)
        return {'source':source,'sha256':hashlib.sha256(raw).hexdigest(),'width':w,'height':h,'path':str(output.resolve()),'selection':'archive icon fallback'}

    def inspect(self):
        return {'source_type':'tar','source':str(self.path.resolve()),'sha256':self.sha256,'metadata':self.metadata,'strip_components':self.strip_components,'desktop_entries':self.desktops,'files':len(self.members),'elf_machines':self.elf_machines}

def prepare_archive(path,config,out):
    path=Path(path);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    expected=config.get('source_sha256') or config.get('archive_sha256')
    if digest!=expected:raise ValueError('Archive SHA256 does not match configuration')
    strip_components,members,_=layout(path,config.get('archive_strip_components'))
    machines=scan_elf(path,strip_components);entry=config['entry'];entry_found=False
    inventory=[];links=[];seen=set()
    payload=out/'payload.tar.gz'
    with tarfile.open(path,'r:*') as src,payload.open('wb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',compresslevel=1,mtime=0) as gz,tarfile.open(fileobj=gz,mode='w|',format=tarfile.PAX_FORMAT) as dest:
        for original in src:
            name=stripped_name(original.name,strip_components)
            if name is None:continue
            if name in seen:raise ValueError('Duplicate path after stripping archive prefix: '+name)
            seen.add(name);m=copy.copy(original);m.name=name
            if not (m.isfile() or m.isdir() or m.issym() or m.islnk()):raise ValueError('Special archive member rejected: '+original.name)
            if m.issym():
                if m.linkname.startswith('/'):raise ValueError('Absolute symlink rejected: '+name)
                resolved=posixpath.normpath(posixpath.join(posixpath.dirname(name),m.linkname))
                if resolved=='..' or resolved.startswith('../'):raise ValueError('Escaping symlink rejected: '+name)
                links.append({'path':name,'target':m.linkname})
            elif m.islnk():
                target=stripped_name(m.linkname,strip_components)
                if target is None:raise ValueError('Hardlink target removed by prefix stripping: '+name)
                m.linkname=target;links.append({'path':name,'target':target})
            m.mode&=0o777;m.uid=m.gid=0;m.uname=m.gname='root';m.mtime=0;m.pax_headers={}
            content=src.extractfile(original) if original.isfile() else None
            if name==entry:
                if not m.isfile() or not (m.mode&0o111):raise ValueError('Entry is not an executable regular file')
                entry_found=True
            inventory.append({'path':name,'size':m.size,'mode':oct(m.mode),'type':m.type.decode('ascii','replace')})
            dest.addfile(m,content)
    if not entry_found:raise ValueError('Configured entry was not found after prefix stripping')
    audit={'source_type':'tar','source_sha256':digest,'archive_strip_components':strip_components,'entry':entry,'files':len(inventory),'symlinks':links,'elf_machines':machines,'maintainer_scripts_executed':False,'setuid_setgid_stripped':True}
    (out/'inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf8');(out/'audit.json').write_text(json.dumps(audit,indent=2),encoding='utf8')
    return payload
