"""ARM64 deb -> validated tar -> EROFS on attached Android -> APK assets.
No maintainer scripts, dpkg installation, or host symlink extraction.
"""
import argparse,gzip,hashlib,io,json,posixpath,re,shlex,struct,subprocess,sys,tarfile,uuid,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import adb_transport as adb
from make_assets import assets

def open_tar(data):
 # Python 3.14 supports zstd natively; earlier Pythons can use python-zstandard.
 if data.startswith(b'\x28\xb5\x2f\xfd'):
  try:
   import compression.zstd
   data=compression.zstd.decompress(data)
  except ImportError:
   try:import zstandard
   except ImportError:raise ValueError('Zstandard deb: install zstandard (python -m pip install zstandard), or use Python 3.14+')
   with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(data)) as stream:data=stream.read()
 return tarfile.open(fileobj=io.BytesIO(data))

def ar_members(path):
 with path.open('rb') as f:
  if f.read(8)!=b'!<arch>\n':raise ValueError('Not a deb/ar archive')
  while h:=f.read(60):
   if len(h)!=60 or h[58:]!=b'`\n':raise ValueError('Invalid ar header')
   size=int(h[48:58]);name=h[:16].decode().strip().rstrip('/')
   data=f.read(size)
   if len(data)!=size:raise ValueError('Truncated ar member')
   if size&1:f.read(1)
   yield name,data

def clean_name(name):
 if name.startswith('/') or '\\' in name or '\x00' in name or '..' in name.split('/'):raise ValueError('Unsafe tar name: '+name)
 return posixpath.normpath(name)

def prepare(deb,config,out):
 with deb.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
 if digest!=config['deb_sha256']:raise ValueError('Deb SHA256 does not match configuration')
 control=None;payload=None
 for name,data in ar_members(deb):
  if name.startswith('control.tar'):
   with open_tar(data) as t:
    m=next(x for x in t if clean_name(x.name)=='control');control=t.extractfile(m).read().decode()
  elif name.startswith('data.tar'):payload=data
 if control is None or payload is None:raise ValueError('Missing deb control/data')
 if not re.search(r'^Architecture: arm64\s*$',control,re.M):raise ValueError('Only Architecture: arm64 is supported')
 out.mkdir(parents=True,exist_ok=True);(out/'control.txt').write_text(control,encoding='utf8')
 inventory=[];links=[];seen=set();entry_found=False
 with open_tar(payload) as src, (out/'payload.tar.gz').open('wb') as raw, gzip.GzipFile(fileobj=raw,mode='wb',compresslevel=1,mtime=0) as gz, tarfile.open(fileobj=gz,mode='w|',format=tarfile.PAX_FORMAT) as dest:
  for m in src:
   m.name=clean_name(m.name)
   if m.name in seen:raise ValueError('Duplicate tar path: '+m.name)
   seen.add(m.name)
   if not (m.isfile() or m.isdir() or m.issym() or m.islnk()):raise ValueError('Special file rejected: '+m.name)
   if m.islnk():m.linkname=clean_name(m.linkname)
   if m.issym():links.append({'path':m.name,'target':m.linkname})
   m.mode&=0o777;m.uid=m.gid=0;m.uname=m.gname='root';m.mtime=0;m.pax_headers={}
   content=src.extractfile(m) if m.isfile() else None
   if m.name==config['entry']:
    if not m.isfile() or not (m.mode&0o111):raise ValueError('Entry is not an executable regular file')
    head=content.read(64);content.seek(0)
    if head[:4]==b'\x7fELF' and (head[4:6]!=b'\x02\x01' or struct.unpack_from('<H',head,18)[0]!=183):raise ValueError('Entry ELF is not ARM64')
    entry_found=True
   inventory.append({'path':m.name,'size':m.size,'mode':oct(m.mode),'type':m.type.decode()})
   dest.addfile(m,content)
 if not entry_found:raise ValueError('Configured entry was not found')
 report={'deb_sha256':digest,'entry':config['entry'],'files':len(inventory),'symlinks':links,'maintainer_scripts_executed':False,'setuid_setgid_stripped':True}
 (out/'inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf8');(out/'audit.json').write_text(json.dumps(report,indent=2),encoding='utf8')
 return out/'payload.tar.gz'

def build_image(payload,out,config):
 # The tar is passed directly into mkfs; symlinks are stored as image metadata.
 remote='/data/local/tmp/pclr-'+hashlib.sha256(config['id'].encode()).hexdigest()[:8]
 print('Sending checked archive to tablet',flush=True)
 su=config.get('adb_su','su')
 adb.shell(shlex.quote(su)+' -M -c '+shlex.quote('mkdir -p '+remote+'; chown 2000:2000 '+remote))
 adb.push(payload,remote+'/payload.tar.gz')
 for name in ['mkfs.erofs','fsck.erofs']:adb.push(ROOT/'tools/erofs-android'/name,remote+'/'+name,0o755)
 imageuuid=str(uuid.uuid5(uuid.NAMESPACE_URL,config.get('source_sha256',config.get('deb_sha256'))))
 script=f'''#!/system/bin/sh
set -eu
{remote}/mkfs.erofs --tar=f --ungzip -zlz4hc --all-root -x-1 -T0 -U{imageuuid} {remote}/application.erofs {remote}/payload.tar.gz
{remote}/fsck.erofs {remote}/application.erofs
chmod 0644 {remote}/application.erofs
'''
 scriptfile=out/'build-image.sh';scriptfile.write_bytes(script.encode());adb.push(scriptfile,remote+'/build-image.sh')
 print('Building and checking EROFS on tablet',flush=True)
 result=adb.shell(shlex.quote(su)+' -M -c '+shlex.quote('sh '+remote+'/build-image.sh; rc=$?; echo __RESULT=$rc'),timeout=600)
 (out/'image-build.log').write_bytes(result)
 if not result.rstrip().endswith(b'__RESULT=0'):raise RuntimeError('EROFS tool reported an error; inspect image-build.log')
 image=out/'application.erofs';adb.pull(remote+'/application.erofs',image)
 with image.open('rb') as f:b=f.read(4096)
 if struct.unpack_from('<I',b,1024)[0]!=0xe0f5e1e2:raise ValueError('EROFS superblock missing')
 print('EROFS received',image.stat().st_size,flush=True);return image

def build_image_wsl(payload,out,config,distro):
 # WSL provides a local x86_64 erofs-utils backend when no tablet is attached.
 if not re.fullmatch(r'[A-Za-z0-9_.-]+',distro):raise ValueError('Invalid WSL distribution name')
 out.mkdir(parents=True,exist_ok=True)
 image=(out/'application.erofs').resolve();payload=Path(payload).resolve()
 def wsl_path(path):
  # wsl.exe parses backslashes before passing argv to Linux; forward slashes
  # preserve an absolute Windows path such as C:/work/application.erofs.
  result=subprocess.run(['wsl.exe','-d',distro,'--','wslpath','-a',str(path).replace('\\','/')],capture_output=True,text=True,timeout=30)
  if result.returncode:raise RuntimeError('WSL path conversion failed: '+result.stderr.strip())
  return result.stdout.strip()
 linux_image=wsl_path(image);linux_payload=wsl_path(payload)
 imageuuid=str(uuid.uuid5(uuid.NAMESPACE_URL,config.get('source_sha256',config.get('deb_sha256'))))
 commands=[
  ['wsl.exe','-d',distro,'--','mkfs.erofs','--tar=f','--ungzip','-zlz4hc','--all-root','-x-1','-T0','-U'+imageuuid,linux_image,linux_payload],
  ['wsl.exe','-d',distro,'--','fsck.erofs',linux_image],
 ]
 log=[]
 if image.exists():image.unlink()
 print('Building and checking EROFS in WSL ('+distro+')',flush=True)
 for command in commands:
  result=subprocess.run(command,capture_output=True,timeout=600)
  log.extend([('$ '+' '.join(shlex.quote(x) for x in command)+'\n').encode(),result.stdout,result.stderr,('exit='+str(result.returncode)+'\n').encode()])
  if result.returncode:
   (out/'image-build.log').write_bytes(b''.join(log))
   raise RuntimeError('EROFS tool reported an error; inspect image-build.log')
 (out/'image-build.log').write_bytes(b''.join(log))
 if not image.is_file():raise RuntimeError('WSL EROFS build did not produce an image')
 with image.open('rb') as f:b=f.read(4096)
 if len(b)<1028 or struct.unpack_from('<I',b,1024)[0]!=0xe0f5e1e2:raise ValueError('EROFS superblock missing')
 print('EROFS created',image.stat().st_size,flush=True);return image

def main():
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=ROOT/'vscode.json');p.add_argument('--deb',type=Path,required=True);p.add_argument('--serial',required=True);p.add_argument('--prepare-only',action='store_true');p.add_argument('--image',type=Path,help='Reuse an already verified EROFS image');a=p.parse_args()
 cfg=json.loads(a.config.read_text(encoding='utf8'));assert re.fullmatch('[a-z][a-z0-9_]{0,31}',cfg['id']);adb.SERIAL=a.serial
 out=ROOT/'staging'/cfg['id'];out.mkdir(parents=True,exist_ok=True)
 payload=prepare(a.deb,cfg,out);print('ARM64 deb checked; archive normalized',flush=True)
 if a.prepare_only:return
 image=a.image or build_image(payload,out,cfg);info=assets(cfg,image,ROOT/'android/assets');(out/'manifest.json').write_text(json.dumps(info,indent=2),encoding='utf8')
 print('Assets ready. Run python build_apk.py',flush=True)
if __name__=='__main__':main()
