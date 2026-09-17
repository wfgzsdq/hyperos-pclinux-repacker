import subprocess,os,zipfile,sys,json,xml.etree.ElementTree as ET
from pathlib import Path
root=Path(__file__).resolve().parent;bt=Path(os.environ.get('PCLINUX_BUILD_TOOLS',root/'tools/build/android-15'));platform=Path(os.environ.get('PCLINUX_ANDROID_JAR',root/'tools/platform/android-13/android.jar'));java=Path(os.environ.get('PCLINUX_JAVA_BIN','C:/Program Files/Microsoft/jdk-17.0.20.101-hotspot/bin'))
b=root/'build';b.mkdir(exist_ok=True);(b/'classes').mkdir(exist_ok=True);(b/'dex').mkdir(exist_ok=True)
def run(args):subprocess.run([str(x) for x in args],check=True)
cfg=json.loads((root/'android/assets/app.json').read_text(encoding='utf8'))
ns='http://schemas.android.com/apk/res/android';ET.register_namespace('android',ns)
manifest=ET.parse(root/'android/AndroidManifest.xml');m=manifest.getroot();m.set('package',cfg['package']);m.set('{'+ns+'}versionCode',str(cfg.get('version_code',1)));m.find('application').set('{'+ns+'}label',cfg['label']);m.find('application/activity').set('{'+ns+'}name','local.pclinux.vscode.MainActivity');manifest.write(b/'AndroidManifest.xml',encoding='utf-8',xml_declaration=True)
run([bt/'aapt2.exe','link','-o',b/'base.apk','--manifest',b/'AndroidManifest.xml','-I',platform])
run([java/'javac.exe','-encoding','UTF-8','-source','8','-target','8','-classpath',platform,'-d',b/'classes',*list((root/'android').glob('*.java'))])
run([java/'java.exe','-cp',bt/'lib/d8.jar','com.android.tools.r8.D8','--lib',platform,'--min-api','30','--output',b/'dex',*list((b/'classes').rglob('*.class'))])
with zipfile.ZipFile(b/'base.apk','a',zipfile.ZIP_DEFLATED) as z:
 z.write(b/'dex/classes.dex','classes.dex')
 assets=root/'android/assets'
 if assets.exists():
  for p in assets.rglob('*'):
   if p.is_file() and not ('--thin' in sys.argv and p.name=='application.erofs'):z.write(p,'assets/'+p.relative_to(assets).as_posix())
run([bt/'zipalign.exe','-f','4',b/'base.apk',b/'aligned.apk'])
key=root/'local-test.jks'
if not key.exists():run([java/'keytool.exe','-genkeypair','-keystore',key,'-storepass','pclinux-local-test','-keypass','pclinux-local-test','-alias','pclinux','-dname','CN=Local PC Linux Test','-keyalg','RSA','-keysize','2048','-validity','3650'])
target=b/(cfg['id']+'-pc.apk')
run([java/'java.exe','-jar',bt/'lib/apksigner.jar','sign','--ks',key,'--ks-pass','pass:pclinux-local-test','--out',target,b/'aligned.apk'])
run([java/'java.exe','-jar',bt/'lib/apksigner.jar','verify','--verbose',target])



