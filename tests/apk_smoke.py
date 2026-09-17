"""Compile a second application identity without requiring a connected tablet.
The output is deliberately thin and is NOT an installable application demo.
"""
import sys,json,zipfile,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_deb2apk import fixture,options
from deb_metadata import Deb
from deb2apk import configure
from make_assets import assets
from apk_builder import build,ROOT

work=ROOT/'jobs/builder_smoke';work.mkdir(parents=True,exist_ok=True)
path=work/'fixture.deb';fixture(path);deb=Deb(path)
try:
 cfg,d=configure(deb,options(id='builder_smoke',scheme=['demo-auth'],url_arg=['--return','@URL@']))
 icon=deb.icon(d,work/'icon.png')
finally:deb.close()
# Dummy image is never bundled: this test isolates the APK/resource builder.
image=work/'not-a-real-image';image.write_bytes(b'APK builder test only')
assets(cfg,image,work/'assets');(work/'assets/launcher-icon.png').write_bytes((work/'icon.png').read_bytes())
apk=build(work/'assets',work/'build',thin=True)
xml=(work/'build/AndroidManifest.xml').read_text()
assert 'local.pclinux.builder_smoke' in xml and 'android:scheme="demo-auth"' in xml
assert 'android:scheme="vscode"' not in xml
assert 'android:icon="@drawable/ic_launcher"' in xml
with zipfile.ZipFile(apk) as z:
 assert any(n.startswith('res/drawable-nodpi') and n.endswith('/ic_launcher.png') for n in z.namelist())
 assert 'assets/application.erofs' not in z.namelist()
 assert json.loads(z.read('assets/app.json'))['id']=='builder_smoke'
assert '/opt/pclinux/vscode/' not in (work/'assets/launch.sh').read_text()
print('PASS: isolated package, custom callback scheme, icon resource, per-app Linux paths; thin build only')
