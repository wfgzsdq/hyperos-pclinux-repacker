"""Build a launcher APK using explicit per-application assets and output paths."""
import argparse,json,os,re,subprocess,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parent
NS='http://schemas.android.com/apk/res/android'
def build(assets,build_dir,output=None,key=None,thin=False):
    bt=Path(os.environ.get('PCLINUX_BUILD_TOOLS',ROOT/'tools/build/android-15'))
    platform=Path(os.environ.get('PCLINUX_ANDROID_JAR',ROOT/'tools/platform/android-13/android.jar'))
    java=Path(os.environ.get('PCLINUX_JAVA_BIN','C:/Program Files/Microsoft/jdk-17.0.20.101-hotspot/bin'))
    for p in [bt/'aapt2.exe',bt/'zipalign.exe',platform,java/'javac.exe']:
        if not p.is_file():raise ValueError('Missing build tool: '+str(p)+'; run setup_tools.py or set PCLINUX_* paths')
    assets=Path(assets);b=Path(build_dir);b.mkdir(parents=True,exist_ok=True)
    for name in ['classes','dex']:(b/name).mkdir(exist_ok=True)
    cfg=json.loads((assets/'app.json').read_text(encoding='utf8'))
    if not re.fullmatch(r'[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,}',cfg['package']):raise ValueError('Invalid Android package ID')
    def run(args):subprocess.run([str(x) for x in args],check=True)
    ET.register_namespace('android',NS);a=lambda s:'{'+NS+'}'+s
    manifest=ET.parse(ROOT/'android/AndroidManifest.xml');m=manifest.getroot()
    m.set('package',cfg['package']);m.set(a('versionCode'),str(cfg.get('version_code',1)));m.set(a('versionName'),cfg.get('version_name','0.3'))
    app=m.find('application');app.set(a('label'),cfg['label']);activity=app.find('activity');activity.set(a('name'),'local.pclinux.vscode.MainActivity')
    for flt in list(activity.findall('intent-filter')):
        if any(x.get(a('name'))=='android.intent.action.VIEW' for x in flt.findall('action')):activity.remove(flt)
    schemes=cfg.get('callback_schemes',[])
    if schemes:
        flt=ET.SubElement(activity,'intent-filter')
        ET.SubElement(flt,'action',{a('name'):'android.intent.action.VIEW'})
        for category in ['DEFAULT','BROWSABLE']:ET.SubElement(flt,'category',{a('name'):'android.intent.category.'+category})
        for scheme in schemes:
            if not re.fullmatch('[a-z][a-z0-9+.-]*',scheme) or scheme in ['http','https','file','content']:raise ValueError('Invalid application callback scheme')
            ET.SubElement(flt,'data',{a('scheme'):scheme})
    compiled=[];icon=assets/'launcher-icon.png'
    if icon.exists():
        res=b/'res/drawable-nodpi';res.mkdir(parents=True,exist_ok=True)
        (res/'ic_launcher.png').write_bytes(icon.read_bytes())
        run([bt/'aapt2.exe','compile','--dir',b/'res','-o',b/'resources.zip'])
        compiled=[b/'resources.zip'];app.set(a('icon'),'@drawable/ic_launcher')
    else:app.set(a('icon'),'@android:drawable/sym_def_app_icon')
    manifest.write(b/'AndroidManifest.xml',encoding='utf-8',xml_declaration=True)
    run([bt/'aapt2.exe','link','-o',b/'base.apk','--manifest',b/'AndroidManifest.xml','-I',platform,*compiled])
    run([java/'javac.exe','-encoding','UTF-8','-source','8','-target','8','-classpath',platform,'-d',b/'classes',*sorted((ROOT/'android').glob('*.java'))])
    run([java/'java.exe','-cp',bt/'lib/d8.jar','com.android.tools.r8.D8','--lib',platform,'--min-api','30','--output',b/'dex',*sorted((b/'classes').rglob('*.class'))])
    with zipfile.ZipFile(b/'base.apk','a',zipfile.ZIP_DEFLATED) as z:
        z.write(b/'dex/classes.dex','classes.dex')
        for p in sorted(assets.iterdir()):
            if p.is_file() and not (thin and p.name=='application.erofs'):z.write(p,'assets/'+p.name)
    run([bt/'zipalign.exe','-f','4',b/'base.apk',b/'aligned.apk'])
    key=Path(key or ROOT/'local-test.jks');key.parent.mkdir(parents=True,exist_ok=True)
    if not key.exists():run([java/'keytool.exe','-genkeypair','-keystore',key,'-storepass','pclinux-local-test','-keypass','pclinux-local-test','-alias','pclinux','-dname','CN=Local PC Linux Test','-keyalg','RSA','-keysize','2048','-validity','3650'])
    target=Path(output or b/(cfg['id']+'-pc.apk'));target.parent.mkdir(parents=True,exist_ok=True)
    run([java/'java.exe','-jar',bt/'lib/apksigner.jar','sign','--ks',key,'--ks-pass','pass:pclinux-local-test','--out',target,b/'aligned.apk'])
    run([java/'java.exe','-jar',bt/'lib/apksigner.jar','verify','--verbose',target])
    return target

def main():
    p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,default=ROOT/'android/assets');p.add_argument('--build-dir',type=Path,default=ROOT/'build');p.add_argument('--output',type=Path);p.add_argument('--key',type=Path);p.add_argument('--thin',action='store_true')
    a=p.parse_args();print(build(a.assets,a.build_dir,a.output,a.key,a.thin))
if __name__=='__main__':main()
