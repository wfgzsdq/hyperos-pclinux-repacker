"""Fetch pinned build tools with published checksum validation (Python stdlib)."""
import concurrent.futures,hashlib,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
JOBS=[
 ('https://dl.google.com/android/repository/platform-33-ext3_r03.zip','platform','394bc86d8d3452aa4d419b67743025a6fb2cd9d0','sha1'),
 ('https://dl.google.com/android/repository/build-tools_r35_windows.zip','build','af059bb67cf7786f45ee0db85e2d24985df1b4b6','sha1'),
 ('https://github.com/sekaiacg/erofs-tools/releases/download/v1.8.10-251217/erofs-utils-v1.8.10-gee46dd74-251217-Android_arm64-v8a.zip','erofs-android','986a3880b7afc0b5efcc58f75268f2c9d03d86773ae8b7ab2c8692215740e21e','sha256')]
def fetch(job):
 url,name,digest,alg=job;p=ROOT/'tools';p.mkdir(exist_ok=True);z=p/(name+'.zip')
 if not z.exists():urllib.request.urlretrieve(url,z)
 with z.open('rb') as f:actual=hashlib.file_digest(f,alg).hexdigest()
 if actual!=digest:raise ValueError(name+' checksum mismatch')
 with zipfile.ZipFile(z) as archive:archive.extractall(p/name)
 print(name,'verified',flush=True)
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:list(ex.map(fetch,JOBS))
