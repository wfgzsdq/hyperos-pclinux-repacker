#!/usr/bin/python3
"""Open a Linux app URL in the Android default browser via its own APK."""
import http.client,json,sys
from pathlib import Path
def main():
 if len(sys.argv)!=2:raise SystemExit('Usage: xdg-open URL')
 with (Path(__file__).resolve().parent/'browser-bridge.json').open() as f:cfg=json.load(f)
 body=json.dumps({'url':sys.argv[1]}).encode()
 conn=http.client.HTTPConnection('127.0.0.1',cfg['port'],timeout=8)
 conn.request('POST','/open',body,{'Authorization':'Bearer '+cfg['token'],'Content-Type':'application/json'})
 response=conn.getresponse();response.read();conn.close()
 if response.status!=204:raise SystemExit('Android browser handoff rejected: '+str(response.status))
if __name__=='__main__':main()
