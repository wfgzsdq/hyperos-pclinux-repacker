from pathlib import Path
import hashlib,json,shutil,zipfile
r=Path(__file__).resolve().parent;out=r.parents[1]/'outputs';out.mkdir(exist_ok=True)
version='0.2';prefix='VSCode-PC-v'+version
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
apk=out/('VSCode-PC-arm64-1.138.0-launcher-v'+version+'.apk')
cfg=json.loads((r/'android/assets/app.json').read_text(encoding='utf8'))
with zipfile.ZipFile(r/'build/vscode-pc.apk') as z:
 info=z.getinfo('assets/application.erofs')
 assert info.file_size==cfg['image_bytes']
 with z.open(info) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==cfg['image_sha256']
shutil.copyfile(r/'build/vscode-pc.apk',apk)
files=['README.md','adb_transport.py','setup_tools.py','download_deb.py','install_apk.py','repack.py','make_assets.py','build_apk.py','package_deliverables_v02.py','vscode.json','android/AndroidManifest.xml','android/MainActivity.java','android/Installer.java','android/Root.java','android/FrameBroker.java','android/InputBridge.java','android/BrowserBridge.java','android/open-browser.py','type_pinyin.py']
source=out/('pclinux-repacker-source-v'+version+'.zip')
with zipfile.ZipFile(source,'w',zipfile.ZIP_DEFLATED) as z:
 for name in files:z.write(r/name,'pclinux-repacker/'+name)
evidence=out/(prefix+'-test-evidence.zip')
names=['poem-candidate1.png','poem-candidate2.png','poem-candidate3.png','poem-candidate4.png','dialog-fixed.png','poem-saved.png','focus-auto.png','appended-x.png','deleted-x.png','poem-verification.json','bridge-verification.json','full-build.log','callback_probe.py','verify_device.py','final_verify.py','login_status.py','login-status.json','final-verification.json','final-install.log']
with zipfile.ZipFile(evidence,'w',zipfile.ZIP_DEFLATED) as z:
 for name in names:z.write(r/'research/v02'/name,'v02/'+name)
poem=json.loads((r/'research/v02/poem-verification.json').read_text(encoding='utf8'))
final=json.loads((r/'research/v02/final-verification.json').read_text(encoding='utf8'))
cfg.update({'vscode_version':'1.138.0','launcher_version':version,'apk_bytes':apk.stat().st_size,'apk_sha256':digest(apk),'test_date':'2026-09-16','device':'Xiaomi 2410CRP4CC (uke)','rootfs':'Ubuntu 22.04.5 ARM64','chinese_test':poem,'final_verification':final,'source_files_sha256':{name:digest(r/name) for name in files}})
manifest=out/(prefix+'-build-manifest.json');manifest.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf8')
report=out/(prefix+'-迭代测试报告.md')
entries=[apk,source,evidence,manifest,report]
(out/(prefix+'-SHA256SUMS.txt')).write_text('\n'.join(digest(p)+'  '+p.name for p in entries)+'\n',encoding='utf8')
for p in [source,evidence]:
 with zipfile.ZipFile(p) as z:assert z.testzip() is None
assert digest(apk)==digest(r/'build/vscode-pc.apk')
print(json.dumps({p.name:p.stat().st_size for p in entries},ensure_ascii=False,indent=2))
