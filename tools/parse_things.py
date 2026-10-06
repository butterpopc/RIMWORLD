import sys, xml.etree.ElementTree as ET, collections, pickle
S=sys.argv[1]
tree=ET.parse(S); root=tree.getroot()
m=root.find('game/maps/li')
things=m.find('things')
rows=[]
for t in things:
    d=t.findtext('def'); cls=t.get('Class'); pos=t.findtext('pos'); 
    stack=t.findtext('stackCount'); stuff=t.findtext('stuff'); fac=t.findtext('faction'); rot=t.findtext('rot')
    hp=t.findtext('health')
    rows.append(dict(def_=d,cls=cls,pos=pos,stack=int(stack) if stack else 1,stuff=stuff,fac=fac,rot=rot,hp=hp,id=t.findtext('id')))
pickle.dump(rows,open('things.pkl','wb'))
c=collections.Counter(r['cls'] for r in rows); print(c.most_common())
# player buildings
pb=[r for r in rows if r['fac']=='Faction_10' or (r['fac'] and 'Player' in (r['fac'] or ''))]
facs=collections.Counter(r['fac'] for r in rows); print(facs.most_common(10))
