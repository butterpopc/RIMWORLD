import sys, re, base64, zlib, struct, collections, json
S=sys.argv[1]
txt=open(S,encoding='utf-8-sig').read()
N=275
def grab(tag, start=0):
    i=txt.index('<'+tag+'>',start); j=txt.index('</'+tag+'>',i)
    return txt[i+len(tag)+2:j], j
def dec(b64, fmt='H'):
    raw=zlib.decompress(base64.b64decode(''.join(b64.split())), -15)
    n=len(raw)//struct.calcsize(fmt)
    return struct.unpack('<%d%s'%(n,fmt), raw)
mi=txt.index('<maps>')
out={}
for tag in ['topGridDeflate','underGridDeflate','roofsDeflate','compressedThingMapDeflate','fogGridDeflate']:
    b,_=grab(tag,mi)
    raw=zlib.decompress(base64.b64decode(''.join(b.split())), -15)
    print(tag, len(raw), len(raw)/(N*N))
    out[tag]=raw
import pickle; pickle.dump(out,open('grids.pkl','wb'))
for tag in ['topGridDeflate','underGridDeflate','roofsDeflate','compressedThingMapDeflate']:
    raw=out[tag]
    a=struct.unpack('<%dH'%(len(raw)//2),raw)
    print(tag, collections.Counter(a).most_common(30))
