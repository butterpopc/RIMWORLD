import pickle,struct,numpy as np,re
from PIL import Image, ImageDraw
N=275
g=pickle.load(open('grids.pkl','rb'))
A=lambda k: np.array(struct.unpack('<%dH'%(N*N),g[k]),dtype=np.int64).reshape(N,N)  # [z][x]
top=A('topGridDeflate'); roof=A('roofsDeflate'); th=A('compressedThingMapDeflate')
T={34465:'Soil',10040:'Sandstone_Rough',56931:'Limestone_Rough',27449:'Marble_Rough',65097:'Gravel',32883:'SoilRich',42032:'Mud',41863:'Marble_RoughHewn',11445:'WaterShallow',38103:'AncientConcrete',63102:'TileMarble',6764:'AncientTile',49581:'FlagstoneSandstone',14838:'Sandstone_RoughHewn',59853:'BrokenAsphalt',50215:'?50215'}
TH={64138:'Limestone',323:'Sandstone',64468:'Marble',27293:'MineableSteel',11383:'ChunkLimestone',45390:'ChunkMarble',13103:'ChunkSandstone',43357:'MineableComponentsIndustrial',21442:'MineableSilver',63717:'MineableGold',7015:'MineableUranium',8319:'MineableJade',23537:'ChunkSlagSteel'}
R={10820:'Thick',6699:'Thin',5133:'Constructed'}
pickle.dump(dict(top=top,roof=roof,th=th,T=T,TH=TH,R=R),open('arr.pkl','wb'))
col={'Soil':(120,95,60),'SoilRich':(80,60,35),'Gravel':(150,140,120),'Mud':(90,75,50),'WaterShallow':(60,110,190),'Sandstone_Rough':(190,150,110),'Limestone_Rough':(200,195,170),'Marble_Rough':(225,225,230),'Marble_RoughHewn':(225,225,230),'Sandstone_RoughHewn':(190,150,110),'AncientConcrete':(110,110,110),'AncientTile':(140,140,150),'TileMarble':(160,160,170),'FlagstoneSandstone':(170,130,90),'BrokenAsphalt':(70,70,70)}
thc={'Limestone':(160,155,125),'Sandstone':(150,105,70),'Marble':(185,185,195),'MineableSteel':(200,60,60),'MineableComponentsIndustrial':(230,200,0),'MineableSilver':(220,220,255),'MineableGold':(255,200,0),'MineableUranium':(0,220,90),'MineableJade':(0,160,110)}
S=4
img=Image.new('RGB',(N*S,N*S)); d=ImageDraw.Draw(img)
for z in range(N):
  for x in range(N):
    c=col.get(T.get(top[z,x]),(255,0,255))
    t=TH.get(th[z,x])
    if t in thc: c=thc[t]
    if R.get(roof[z,x])=='Thick' and t in ('Limestone','Sandstone','Marble'):
        c=tuple(int(v*0.6) for v in c)
    yy=(N-1-z)*S
    d.rectangle([x*S,yy,x*S+S-1,yy+S-1],fill=c)
rows=pickle.load(open('things.pkl','rb'))
def P(s): a=re.findall(r'-?\d+',s); return int(a[0]),int(a[2])
for r in rows:
  if not r['pos']: continue
  x,z=P(r['pos']); yy=(N-1-z)*S
  if r['fac']=='Faction_152' and r['cls']!='Pawn':
    d.rectangle([x*S,yy,x*S+S-1,yy+S-1],fill=(255,0,255))
  elif r['def_'] in ('SteamGeyser',):
    d.ellipse([x*S-4,yy-4,x*S+12,yy+12],outline=(0,255,255),width=2)
  elif r['def_'] in ('VoidMonolith','Hive','Plant_TreeAnima','AncientMechDropBeacon'):
    d.ellipse([x*S-6,yy-6,x*S+14,yy+14],outline=(255,0,0),width=2)
for i in range(0,N,25):
  d.line([(i*S,0),(i*S,N*S)],fill=(0,0,0),width=1); d.line([(0,(N-1-i)*S+S),(N*S,(N-1-i)*S+S)],fill=(0,0,0),width=1)
img.save('map.png')
import collections
print(collections.Counter(T.get(v,v) for v in top.flat))
