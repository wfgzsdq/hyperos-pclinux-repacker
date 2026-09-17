"""Install a built APK through the running local ADB server."""
import argparse,shlex
from pathlib import Path
import adb_transport as adb
def main():
 p=argparse.ArgumentParser();p.add_argument('apk',type=Path);p.add_argument('--serial',required=True);a=p.parse_args();adb.SERIAL=a.serial
 remote='/data/local/tmp/pclinux-install.apk';adb.push(a.apk,remote)
 result=adb.shell('pm install -r '+shlex.quote(remote),timeout=180).decode('utf8','replace');print(result)
 if 'Success' not in result:raise RuntimeError('APK installation failed')
 adb.shell('rm -f '+shlex.quote(remote))
if __name__=='__main__':main()
