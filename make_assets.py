import json,hashlib,shutil,shlex,re
from pathlib import Path
root=Path(__file__).resolve().parent
def assets(cfg,image,dest):
 c=dict(cfg);ident=c['id'];assert re.fullmatch('[a-z][a-z0-9_]{0,31}',ident)
 assert re.fullmatch(r'[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,}',c['package'])
 entry=c['entry'];assert not entry.startswith('/') and '..' not in entry.split('/')
 with image.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
 c['image_sha256']=digest;c['image_bytes']=image.stat().st_size
 c['image_path']='/data/rootfs/pclimg/'+digest[:16]+'.erofs'
 dest.mkdir(parents=True,exist_ok=True)
 target_image=dest/'application.erofs'
 existing=None
 if target_image.exists():
  with target_image.open('rb') as f:existing=hashlib.file_digest(f,'sha256').hexdigest()
 if existing!=digest:shutil.copyfile(image,target_image)
 (dest/'app.json').write_text(json.dumps(c,ensure_ascii=False,indent=2),encoding='utf8')
 app='/opt/pclinux/'+ident+'/'+digest[:16];data='/home/xiaomi/.pclinux/'+ident
 expand=lambda x:x.replace('@APP@',app).replace('@DATA@',data)
 args=[expand(x) for x in c['args']]
 bridge='/opt/pclinux/'+ident+'/bridge'
 launch='''#!/bin/sh
set -eu
cd '''+shlex.quote(data)+'''
bus=$(cat /opt/pclinux/'''+ident+'''/dbus-address)
exec /usr/bin/env -i DBUS_SESSION_BUS_ADDRESS="$bus" HOME=/home/xiaomi USER=product_hyperengine LOGNAME=product_hyperengine SHELL=/bin/bash PATH=/usr/local/bin:/usr/bin:/bin TMPDIR=/tmp LANG=C.UTF-8 DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/mnt/mslg/runtime-dir PULSE_SERVER=/mnt/mslg/PulseServer GTK_IM_MODULE=fcitx QT_IM_MODULE=fcitx XMODIFIERS=@im=fcitx '''+' '.join(shlex.quote(x) for x in [app+'/'+entry]+args)+'\n'
 deploy=f'''#!/system/bin/sh
set -eu
image={c['image_path']}
target=/data/rootfs{app}
state=/data/rootfs{data}
test -x /data/rootfs/usr/bin/weston || {{ echo '请先开启小米 PC 框架（打开一次 WPS PC 或 CAJViewer PC），再重试。'; exit 2; }}
mkdir -p /data/rootfs/pclimg "$target" "$state"
if [ ! -f "$image" ]; then
    cp "$1" "$image.new"
    echo '{digest}  '"$image.new" | sha256sum -c - || exit 3
    chmod 0600 "$image.new"
    chcon u:object_r:mslg_rootfs_file:s0 "$image.new"
    mv "$image.new" "$image"
fi
echo '{digest}  '"$image" | sha256sum -c - || exit 3
if ! grep -qs " $target " /proc/mounts; then
    mount -t erofs -o loop,ro,nosuid,nodev "$image" "$target"
fi
test -x {shlex.quote('/data/rootfs'+app+'/'+entry)}
cp "$2" /data/rootfs/opt/pclinux/{ident}/launch.sh
chmod 0755 /data/rootfs/opt/pclinux/{ident}/launch.sh
chown 7100:7100 /data/rootfs/home/xiaomi/.pclinux "$state"
bus=""
for pid in $(pidof fcitx5); do
    bus=$(tr '\\000' '\\n' </proc/$pid/environ | sed -n 's/^DBUS_SESSION_BUS_ADDRESS=//p')
    [ -z "$bus" ] || break
done
printf '%s' "$bus" >/data/rootfs/opt/pclinux/{ident}/dbus-address
chmod 0644 /data/rootfs/opt/pclinux/{ident}/dbus-address
nohup /vendor/bin/chroot /data/rootfs /bin/su -s /bin/sh product_hyperengine -c /opt/pclinux/{ident}/launch.sh >"$state/launcher.log" 2>&1 </dev/null &
echo launched
'''
 launch=launch.replace('PATH=/usr/local/bin:/usr/bin:/bin','PATH='+bridge+':/usr/local/bin:/usr/bin:/bin BROWSER='+bridge+'/xdg-open')
 environment=[]
 for name,value in c.get('env',{}).items():
  if not re.fullmatch('[A-Z_][A-Z0-9_]*',name) or not isinstance(value,str):raise ValueError('Invalid environment entry')
  if name in ('PATH','BROWSER','DBUS_SESSION_BUS_ADDRESS'):raise ValueError('Environment variable reserved by the bridge: '+name)
  environment.append(shlex.quote(name+'='+expand(value)))
 if environment:launch=launch.replace('XMODIFIERS=@im=fcitx ','XMODIFIERS=@im=fcitx '+' '.join(environment)+' ')
 # Some applications require these XDG directories to exist before first launch.
 launch=launch.replace('set -eu\n','set -eu\nmkdir -p '+ ' '.join(shlex.quote(data+'/'+d) for d in ['home','config','cache','data'])+'\n',1)
 if c.get('single_instance_lock',False):
  deploy=deploy.replace('-c /opt/pclinux/'+ident+'/launch.sh','-c '+shlex.quote('/usr/bin/flock -n '+data+'/application.lock /opt/pclinux/'+ident+'/launch.sh'))
 launch=launch.rstrip()+' "$@"\n'
 setup=f'''mkdir -p /data/rootfs{bridge}
cp "$3" /data/rootfs{bridge}/browser-bridge.json
cp "$4" /data/rootfs{bridge}/open-browser.py
cp "$5" /data/rootfs{bridge}/xdg-open
chown -R 7100:7100 /data/rootfs{bridge}
chmod 0700 /data/rootfs{bridge}
chmod 0600 /data/rootfs{bridge}/browser-bridge.json
chmod 0755 /data/rootfs{bridge}/open-browser.py /data/rootfs{bridge}/xdg-open
'''
 deploy=deploy.replace('nohup /vendor/bin/chroot',setup+'nohup /vendor/bin/chroot')
 (dest/'open-browser.py').write_bytes((root/'android/open-browser.py').read_bytes().replace(b'\r\n',b'\n'))
 (dest/'xdg-open').write_bytes(('#!/bin/sh\nexec /usr/bin/python3 '+bridge+'/open-browser.py "$@"\n').encode())
 (dest/'launch.sh').write_bytes(launch.encode());(dest/'deploy.sh').write_bytes(deploy.encode());return c
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(description='Generate launcher assets from a checked EROFS image')
 p.add_argument('--config',type=Path,default=root/'vscode.json')
 p.add_argument('--image',type=Path)
 p.add_argument('--dest',type=Path,default=root/'android/assets')
 a=p.parse_args();cfg=json.loads(a.config.read_text(encoding='utf8'))
 c=assets(cfg,a.image or root/'staging'/cfg['id']/'application.erofs',a.dest)
 print(json.dumps(c,ensure_ascii=False,indent=2))
