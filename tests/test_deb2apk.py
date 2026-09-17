import gzip,io,json,lzma,struct,sys,tarfile,tempfile,unittest,zlib
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deb_metadata import Deb
from archive_metadata import Archive,prepare_archive
from deb2apk import configure,validate
from make_assets import assets
from repack import prepare,build_image_wsl
def png_chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
PNG=b'\x89PNG\r\n\x1a\n'+png_chunk(b'IHDR',struct.pack('>IIBBBBB',16,16,8,6,0,0,0))+png_chunk(b'IDAT',zlib.compress((b'\0'+b'\0\x80\xff\xff'*16)*16))+png_chunk(b'IEND',b'')

def archive(entries,compression='xz'):
    b=io.BytesIO()
    with tarfile.open(fileobj=b,mode='w') as t:
        for name,data,mode,link in entries:
            m=tarfile.TarInfo(name);m.mode=mode
            if link is not None:m.type=tarfile.SYMTYPE;m.linkname=link;t.addfile(m)
            else:m.size=len(data);t.addfile(m,io.BytesIO(data))
    return lzma.compress(b.getvalue()) if compression=='xz' else gzip.compress(b.getvalue())

def fixture(path,arch='arm64',extra=(),desktop=True,compression='xz'):
    desktop_text=b'[Desktop Entry]\nType=Application\nName=Demo Editor\nExec=demo --new-window %F\nIcon=demo\n'
    entries=[('./usr/bin/demo',b'',0o777,'../lib/demo/run'),('./usr/lib/demo/run',b'#!/bin/sh\nexit 0\n',0o755,None),('./usr/share/pixmaps/demo.png',PNG,0o644,None)]
    if desktop:entries.append(('./usr/share/applications/demo.desktop',desktop_text,0o644,None))
    entries.extend(extra)
    control=('Package: demo-editor\nVersion: 1.0\nArchitecture: '+arch+'\nDepends: libc6 (>= 2.35)\n').encode()
    members=[('debian-binary',b'2.0\n'),('control.tar.'+compression,archive([('./control',control,0o644,None)],compression)),('data.tar.'+compression,archive(entries,compression))]
    with path.open('wb') as f:
        f.write(b'!<arch>\n')
        for name,data in members:
            f.write(f'{name+"/":<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(data):<10}`\n'.encode());f.write(data)
            if len(data)%2:f.write(b'\n')

def options(**kw):
    a={k:None for k in ['config','entry','desktop','preset','id','package','label','version_code','version_name','arg','scheme','url_arg','env','adb_su']};a.update(kw);return SimpleNamespace(**a)

def tar_fixture(path,machine=183,escape=False):
    elf=bytearray(64);elf[:6]=b'\x7fELF\x02\x01';struct.pack_into('<H',elf,18,machine)
    desktop=b'[Desktop Entry]\nType=Application\nName=Archive Demo\nExec=demo %U\nIcon=demo\nMimeType=x-scheme-handler/demo;\n'
    with tarfile.open(path,'w:xz') as t:
        for name,data,mode,kind,link in [
            ('Demo-arm64',b'',0o755,'dir',''),('Demo-arm64/demo',bytes(elf),0o755,'file',''),
            ('Demo-arm64/demo.desktop',desktop,0o644,'file',''),('Demo-arm64/icons/demo.png',PNG,0o644,'file','')]:
            m=tarfile.TarInfo(name);m.mode=mode
            if kind=='dir':m.type=tarfile.DIRTYPE;t.addfile(m)
            else:m.size=len(data);t.addfile(m,io.BytesIO(data))
        if escape:
            m=tarfile.TarInfo('Demo-arm64/bad');m.type=tarfile.SYMTYPE;m.linkname='../../outside';t.addfile(m)

class Tests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.path=self.root/'demo.deb';fixture(self.path)
    def tearDown(self):self.temp.cleanup()
    def test_desktop_exec_symlink_and_fields(self):
        d=Deb(self.path)
        try:
            cfg,desktop=configure(d,options());self.assertEqual(cfg['entry'],'usr/lib/demo/run');self.assertEqual(cfg['args'],['--new-window']);self.assertEqual(cfg['id'],'demo_editor');self.assertEqual(cfg['callback_schemes'],[])
            info=d.icon(desktop,self.root/'icon.png');self.assertEqual((self.root/'icon.png').read_bytes(),PNG);self.assertEqual(info['source'],'usr/share/pixmaps/demo.png')
        finally:d.close()
    def test_normalization_retains_links_and_executable(self):
        d=Deb(self.path)
        try:cfg,_=configure(d,options())
        finally:d.close()
        payload=prepare(self.path,cfg,self.root/'image')
        with tarfile.open(payload) as t:
            self.assertTrue(t.getmember('usr/bin/demo').issym());self.assertEqual(t.getmember('usr/lib/demo/run').uid,0)
    def test_gzip_supported(self):
        fixture(self.path,compression='gz');d=Deb(self.path);self.assertEqual(d.metadata['Architecture'],'arm64');d.close()
    def test_wrong_architecture_rejected(self):
        fixture(self.path,arch='amd64')
        with self.assertRaisesRegex(ValueError,'arm64'):Deb(self.path)
    def test_path_traversal_rejected(self):
        fixture(self.path,extra=[('../escape',b'x',0o644,None)])
        with self.assertRaisesRegex(ValueError,'Unsafe'):Deb(self.path)
    def test_multiple_launchers_require_selection(self):
        fixture(self.path,extra=[('./usr/share/applications/second.desktop',b'[Desktop Entry]\nType=Application\nExec=demo\nName=Second\n',0o644,None)])
        d=Deb(self.path)
        try:
            with self.assertRaisesRegex(ValueError,'Choose --desktop'):configure(d,options())
            cfg,_=configure(d,options(desktop='second.desktop'));self.assertEqual(cfg['label'],'Second PC')
        finally:d.close()
    def test_library_without_desktop_requires_explicit_entry(self):
        fixture(self.path,desktop=False);d=Deb(self.path)
        try:
            with self.assertRaises(ValueError):configure(d,options())
            cfg,_=configure(d,options(entry='usr/bin/demo'));self.assertEqual(cfg['entry'],'usr/lib/demo/run')
        finally:d.close()
    def test_callback_and_shell_quoting_are_app_scoped(self):
        d=Deb(self.path)
        try:cfg,_=configure(d,options(id='second_app',scheme=['demo-auth'],url_arg=['--return','@URL@'],arg=['$(do-not-execute)',"a'b"],env=['TEST_ARG=a b;$HOME']))
        finally:d.close()
        image=self.root/'fake.erofs';image.write_bytes(b'metadata-test-only')
        assets(cfg,image,self.root/'assets')
        s=(self.root/'assets/launch.sh').read_text();self.assertIn("'$(do-not-execute)'",s);self.assertIn("'TEST_ARG=a b;$HOME'",s);self.assertNotIn('/opt/pclinux/vscode',s)
        self.assertEqual(cfg['package'],'local.pclinux.second_app')
        self.assertIn('/second_app/',(self.root/'assets/deploy.sh').read_text())
    def test_web_scheme_and_missing_url_placeholder_rejected(self):
        d=Deb(self.path)
        try:
            with self.assertRaisesRegex(ValueError,'scheme'):configure(d,options(scheme=['https']))
            with self.assertRaisesRegex(ValueError,'@URL@'):configure(d,options(scheme=['demo'],url_arg=['--return']))
        finally:d.close()
    def test_deb_hash_mismatch_rejected(self):
        p=self.root/'config.json';p.write_text(json.dumps({'deb_sha256':'0'*64}));d=Deb(self.path)
        try:
            with self.assertRaisesRegex(ValueError,'does not match'):configure(d,options(config=p))
        finally:d.close()
    def test_tar_distribution_strips_single_root_and_normalizes(self):
        p=self.root/'archive-demo_linux-arm64.tar.xz';tar_fixture(p);d=Archive(p)
        try:
            self.assertEqual(d.strip_components,1);cfg,desktop=configure(d,options())
            self.assertEqual(cfg['entry'],'demo');self.assertEqual(cfg['source_type'],'tar')
            self.assertEqual(d.icon(desktop,self.root/'archive-icon.png')['source'],'icons/demo.png')
        finally:d.close()
        payload=prepare_archive(p,cfg,self.root/'archive-image')
        with tarfile.open(payload) as t:
            self.assertIn('demo',t.getnames());self.assertNotIn('Demo-arm64/demo',t.getnames())
    def test_tar_non_arm64_elf_rejected(self):
        p=self.root/'wrong.tar.xz';tar_fixture(p,machine=62)
        with self.assertRaisesRegex(ValueError,'Non-ARM64'):Archive(p)
    def test_tar_escaping_symlink_rejected_during_normalization(self):
        p=self.root/'escape.tar.xz';tar_fixture(p,escape=True);d=Archive(p)
        try:cfg,_=configure(d,options())
        finally:d.close()
        with self.assertRaisesRegex(ValueError,'Escaping symlink'):prepare_archive(p,cfg,self.root/'escape-image')
    def test_wsl_distribution_name_is_validated(self):
        with self.assertRaisesRegex(ValueError,'Invalid WSL'):
            build_image_wsl(self.root/'payload.tar.gz',self.root/'image',{'source_sha256':'0'*64},'bad name; command')

if __name__=='__main__':unittest.main()
