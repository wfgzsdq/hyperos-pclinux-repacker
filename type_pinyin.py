import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from adb_transport import shell,push
# Gboard landscape layout observed at 3200x2136, Simplified Chinese / Pinyin.
coords={}
for letters,xs,y in [('qwertyuiop',[457,711,968,1227,1477,1736,1982,2238,2497,2754],1436),('asdfghjkl',[518,779,1027,1282,1536,1792,2050,2304,2556],1620),('zxcvbnm',[640,895,1150,1402,1653,1914,2170],1804)]:
 coords.update({c:(x,y) for c,x in zip(letters,xs)})
phrase=sys.argv[1] if len(sys.argv)>1 else 'guanguanjujiu'
script='#!/system/bin/sh\n'+''.join('input tap %d %d\n'%coords[c] for c in phrase)
file=Path(__file__).resolve().parent/'pinyin-taps.sh';file.write_bytes(script.encode());push(file,'/data/local/tmp/pclinux-pinyin-taps.sh')
print(shell('sh /data/local/tmp/pclinux-pinyin-taps.sh',timeout=180).decode())
print('Typed pinyin through Gboard keys:',phrase)
