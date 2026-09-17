"""Download the exact deb configured for a local build; validate SHA256."""
import argparse,hashlib,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=ROOT/'vscode.json');p.add_argument('--out',type=Path);a=p.parse_args()
 cfg=json.loads(a.config.read_text(encoding='utf8'));out=a.out or ROOT/'downloads'/(cfg['id']+'-arm64.deb');out.parent.mkdir(parents=True,exist_ok=True)
 def valid(path):
  with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()==cfg['deb_sha256']
 if out.exists() and valid(out):print('Already verified:',out);return
 temp=out.with_suffix('.deb.part')
 urllib.request.urlretrieve(cfg['source_url'],temp)
 if not valid(temp):raise ValueError('Downloaded deb SHA256 mismatch; final file unchanged')
 temp.replace(out);print('Downloaded and verified:',out)
if __name__=='__main__':main()
