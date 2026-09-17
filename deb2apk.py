"""Configurable ARM64 deb or relocatable tar distribution -> Xiaomi APK.

This relocates a package; it does not provide an arbitrary Linux distribution,
resolve apt dependencies, execute maintainer scripts, or install the result.
"""
import argparse,hashlib,json,re,shlex,struct,subprocess,sys,tarfile
from pathlib import Path
from deb_metadata import Deb
from archive_metadata import Archive,prepare_archive
from repack import prepare,build_image,build_image_wsl
from make_assets import assets
from apk_builder import build
import adb_transport as adb
ROOT=Path(__file__).resolve().parent

def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def validate(cfg):
    if not re.fullmatch('[a-z][a-z0-9_]{0,31}',cfg['id']):raise ValueError('id must match [a-z][a-z0-9_]{0,31}')
    if not re.fullmatch(r'[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,}',cfg['package']):raise ValueError('Invalid Android package ID')
    if type(cfg.get('version_code',1)) is not int or not 1<=cfg.get('version_code',1)<=2100000000:raise ValueError('Invalid Android version_code')
    for key in ['args','callback_args','callback_schemes']:
        if not isinstance(cfg.get(key,[]),list) or any(not isinstance(x,str) or '\0' in x or '\n' in x or '\r' in x for x in cfg.get(key,[])):raise ValueError(key+' must be a list of single-line strings')
    for s in cfg.get('callback_schemes',[]):
        if not re.fullmatch('[a-z][a-z0-9+.-]*',s) or s in ['http','https','file','content']:raise ValueError('Invalid callback scheme: '+s)
    if cfg.get('callback_schemes') and cfg.get('callback_args',[]).count('@URL@')!=1:raise ValueError('callback_args must contain exactly one separate @URL@ argument')
    if not isinstance(cfg.get('env',{}),dict):raise ValueError('env must be a JSON object')
    for k,v in cfg.get('env',{}).items():
        if not re.fullmatch('[A-Z_][A-Z0-9_]*',k) or not isinstance(v,str) or '\0' in v:raise ValueError('Invalid environment override')
        if k in ['PATH','BROWSER','DBUS_SESSION_BUS_ADDRESS']:raise ValueError('Reserved bridge environment variable: '+k)

def configure(deb,a):
    custom=json.loads(a.config.read_text(encoding='utf-8-sig')) if a.config else {}
    expected=custom.get('source_sha256') or custom.get('archive_sha256') or custom.get('deb_sha256')
    if expected and expected!=deb.sha256:raise ValueError('Input package does not match configured source SHA256; inspect and update the config for this version')
    rawid=re.sub('[^a-z0-9_]','_',deb.metadata.get('Package','application').lower())
    if not rawid or not rawid[0].isalpha():rawid='app_'+rawid
    ident=rawid if len(rawid)<=32 else rawid[:23]+'_'+hashlib.sha256(rawid.encode()).hexdigest()[:8]
    entry=a.entry or custom.get('entry');desktop=a.desktop or custom.get('desktop_file');d={};path=''
    if desktop or not entry:path,d=deb.select_desktop(desktop)
    elif deb.desktops:
        try:path,d=deb.select_desktop()
        except ValueError:pass
    if entry:entry=deb.executable(entry);arguments=[]
    else:entry,arguments=deb.command(path,d)
    source_type='deb' if isinstance(deb,Deb) and not isinstance(deb,Archive) else 'tar'
    cfg={'id':ident,'package':'local.pclinux.'+ident,'label':d.get('Name',deb.metadata.get('Package',ident))+' PC','version_code':1,'version_name':'0.3','entry':entry,'args':arguments,'source_type':source_type,'source_sha256':deb.sha256,'desktop_file':path,'callback_schemes':[],'callback_args':[],'single_instance_lock':True,'env':{'HOME':'@DATA@/home','XDG_CONFIG_HOME':'@DATA@/config','XDG_CACHE_HOME':'@DATA@/cache','XDG_DATA_HOME':'@DATA@/data','XDG_DATA_DIRS':'@APP@/usr/share:/usr/local/share:/usr/share'}}
    if source_type=='deb':cfg['deb_sha256']=deb.sha256
    else:cfg['archive_strip_components']=deb.strip_components
    known_code=entry in ['usr/share/code/code','usr/share/code-insiders/code-insiders']
    preset=a.preset or custom.get('preset','auto')
    if preset=='electron' or (preset=='auto' and known_code):
        cfg['args']=['--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--ozone-platform=x11']+arguments
    if preset=='auto' and known_code:
        cfg['args']+=['--reuse-window','--user-data-dir=@DATA@','--extensions-dir=@DATA@/extensions']
        cfg['env']={};cfg['single_instance_lock']=False
        cfg['callback_schemes']=['vscode-insiders' if 'insiders' in entry else 'vscode'];cfg['callback_args']=['--open-url','@URL@']
    cfg.update(custom);cfg['entry']=entry;cfg['source_type']=source_type;cfg['source_sha256']=deb.sha256
    if source_type=='deb':cfg['deb_sha256']=deb.sha256
    for key in ['id','package','label','version_code','version_name']:
        if getattr(a,key,None) is not None:cfg[key]=getattr(a,key)
    if a.id and not a.package and 'package' not in custom:cfg['package']='local.pclinux.'+a.id
    if a.arg is not None:cfg['args']=a.arg
    if a.scheme is not None:cfg['callback_schemes']=a.scheme;cfg['callback_args']=a.url_arg or ['@URL@']
    elif a.url_arg is not None:cfg['callback_args']=a.url_arg
    for item in a.env or []:
        if '=' not in item:raise ValueError('--env requires NAME=VALUE')
        k,v=item.split('=',1);cfg.setdefault('env',{})[k]=v
    if a.adb_su:cfg['adb_su']=a.adb_su
    validate(cfg)
    return cfg,d

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('source',type=Path);p.add_argument('--inspect',action='store_true',help='Print metadata/desktop choices; no tablet or build tools needed')
    p.add_argument('--configure-only',action='store_true',help='Write editable app.json and icon without building')
    p.add_argument('--config',type=Path);p.add_argument('--desktop');p.add_argument('--entry');p.add_argument('--id');p.add_argument('--package');p.add_argument('--label');p.add_argument('--version-code',type=int);p.add_argument('--version-name')
    p.add_argument('--arg',action='append',help='Replace launch args; repeat --arg=VALUE (including values starting with --)')
    p.add_argument('--env',action='append');p.add_argument('--scheme',action='append');p.add_argument('--url-arg',action='append');p.add_argument('--preset',choices=['auto','generic','electron'])
    p.add_argument('--icon',type=Path,help='Override with a local PNG; otherwise use desktop Icon from the deb')
    p.add_argument('--icon-member',help='Use a PNG path inside the package/archive')
    p.add_argument('--strip-components',type=int,help='Tar only: remove this many leading path components')
    p.add_argument('--serial');p.add_argument('--adb-su',help='ADB root executable, e.g. /debug_ramdisk/su')
    p.add_argument('--wsl-distro',help='Build EROFS locally with mkfs.erofs/fsck.erofs in this WSL distribution')
    p.add_argument('--work-dir',type=Path);p.add_argument('--output',type=Path);p.add_argument('--key',type=Path)
    p.add_argument('--reuse-image',type=Path,help='Reuse an image previously built from this exact source package')
    p.add_argument('--image-sha256',help='Required expected digest with --reuse-image')
    a=p.parse_args();pre=json.loads(a.config.read_text(encoding='utf-8-sig')) if a.config else {}
    strip=a.strip_components if a.strip_components is not None else pre.get('archive_strip_components')
    if a.source.suffix.lower()=='.deb':deb=Deb(a.source)
    elif tarfile.is_tarfile(a.source):deb=Archive(a.source,strip)
    else:raise ValueError('Unsupported input: expected .deb or a tar archive (tar.xz/tar.gz/tar.bz2/tar)')
    try:
        metadata=deb.inspect()
        if a.inspect:print(json.dumps(metadata,ensure_ascii=False,indent=2));return
        cfg,desktop=configure(deb,a)
        work=(a.work_dir or ROOT/'jobs'/cfg['id']).resolve();work.mkdir(parents=True,exist_ok=True)
        icon=deb.icon(desktop,work/'launcher-icon.png',a.icon,a.icon_member or cfg.get('icon_member'))
        cfg['icon_provenance']={k:v for k,v in icon.items() if k!='path'} if icon else None
        (work/'app.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf8')
        (work/'deb-inspection.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf8')
        warnings=['Dependencies are reported, not automatically installed: '+deb.metadata.get('Depends','(none declared)'),'Relocated launch may need --entry, --arg or --env; maintainer scripts will not run.']
        if cfg['source_type']=='tar':warnings.append('Archive bundles are self-contained only to the extent documented by their publisher; host library compatibility is not automatically resolved.')
        if not icon:warnings.append('No matching PNG icon found; Android generic icon will be used. Use --icon for SVG-only packages.')
        head=deb.tar.extractfile(deb.members[cfg['entry']]).read(4)
        if head!=b'\x7fELF':warnings.append('Entry is a script: check embedded absolute paths before assuming it can be relocated.')
        (work/'compatibility.txt').write_text('\n'.join(warnings)+'\n',encoding='utf8')
        print('Configuration:',work/'app.json',flush=True)
        for warning in warnings:print('NOTE:',warning,flush=True)
        if a.configure_only:return
    finally:deb.close()
    if a.reuse_image:
        if not a.image_sha256 or digest(a.reuse_image)!=a.image_sha256.lower():raise ValueError('--reuse-image requires its matching --image-sha256')
        with a.reuse_image.open('rb') as f:head=f.read(4096)
        if len(head)<1028 or struct.unpack_from('<I',head,1024)[0]!=0xe0f5e1e2:raise ValueError('Not an EROFS image')
        image=a.reuse_image
    else:
        payload=prepare(a.source,cfg,work/'image') if cfg['source_type']=='deb' else prepare_archive(a.source,cfg,work/'image')
        if a.serial and a.wsl_distro:raise ValueError('Choose one EROFS builder: --serial or --wsl-distro')
        if a.wsl_distro:image=build_image_wsl(payload,work/'image',cfg,a.wsl_distro)
        elif a.serial:
            adb.SERIAL=a.serial
            root_ok=False
            for candidate in ([cfg['adb_su']] if cfg.get('adb_su') else ['su','/debug_ramdisk/su','/sbin/su']):
                if adb.shell(shlex.quote(candidate)+' -M -c '+shlex.quote('id -u')).strip()==b'0':
                    cfg['adb_su']=candidate;root_ok=True;break
            if not root_ok:raise ValueError('ADB shell has no usable root; check authorization or specify --adb-su')
            image=build_image(payload,work/'image',cfg)
        else:raise ValueError('Building EROFS requires --serial for a rooted tablet or --wsl-distro with erofs-utils')
    manifest=assets(cfg,image,work/'assets')
    target_icon=work/'assets/launcher-icon.png'
    if icon:target_icon.write_bytes((work/'launcher-icon.png').read_bytes())
    elif target_icon.exists():target_icon.unlink()
    output=(a.output or work/(cfg['id']+'-pc.apk')).resolve()
    build(work/'assets',work/'build',output,a.key)
    manifest.update({'apk_sha256':digest(output),'apk_bytes':output.stat().st_size,'image_reused':bool(a.reuse_image),'icon':cfg['icon_provenance']})
    output.with_suffix('.build.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print('APK:',output,flush=True)

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,RuntimeError,subprocess.CalledProcessError) as e:raise SystemExit('ERROR: '+str(e))
