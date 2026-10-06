import sys, xml.etree.ElementTree as ET
root=ET.parse(sys.argv[1]).getroot()
m=root.find('game/maps/li')
for t in m.find('things'):
    if t.findtext('def')!='Human' or t.findtext('faction')!='Faction_152': continue
    nm=t.find('name'); 
    print('=====',t.findtext('id'), nm.findtext('first'), nm.findtext('nick'), nm.findtext('last'), t.findtext('gender'))
    print('age ticks', t.findtext('ageTracker/ageBiologicalTicks'))
    print('xeno', t.findtext('genes/xenotype'), t.findtext('genes/xenotypeName'))
    print('backstory', t.findtext('story/childhood'), '/', t.findtext('story/adulthood'))
    print('traits', [(x.findtext('def'), x.findtext('degree')) for x in t.findall('story/traits/allTraits/li')])
    sk=[]
    for s in t.findall('skills/skills/li'):
        sk.append((s.findtext('def'), s.findtext('level') or '0', s.findtext('passion') or ''))
    print('skills', sk)
    print('hediffs', [(h.findtext('def'), h.findtext('part/index') if h.find('part') is not None else '', h.findtext('severity')) for h in t.findall('healthTracker/hediffSet/hediffs/li')])
    print('ideo', t.findtext('ideo/ideo'))
    print('workDisabled?', t.findtext('story/disabledWorkTags'))
    ab=[a.findtext('def') for a in t.findall('abilities/abilities/li')]; print('abilities',ab)
    print('royalty titles', [x.findtext('def') for x in t.findall('royalty/titles/li')])
    print('genes', [g.findtext('def') for g in t.findall('genes/endogenes/li')][:40], [g.findtext('def') for g in t.findall('genes/xenogenes/li')])
