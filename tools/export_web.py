# -*- coding: utf-8 -*-
"""지형 + 청사진 + 기존 구조물/특수지형을 웹 뷰어용 JSON 한 덩어리로 내보냄.
사용: python3 -I tools/export_web.py <arr.pkl> <things.pkl> <layout.json> <out.json>
지형 문자: . 흙  * 비옥토  , 자갈  ~ 진흙  w 얕은물  s/l/m 암석 바닥(사암/석회암/대리석)  t 고대 바닥
          S/L/M 암벽  $ 강철  C 부품  A 은  G 금  U 우라늄  J 비취  o 돌덩이
          지붕은 roof 문자열에 별도: 0=없음 1=두꺼운 산 지붕 2=건설 지붕 3=얇은 암석 지붕
"""
import json, pickle, re, sys

arr_pkl, things_pkl, layout, out = sys.argv[1:5]
D = pickle.load(open(arr_pkl, "rb"))
top, roof, th, T, TH, R = [D[k] for k in "top roof th T TH R".split()]
N = 275
gc = {"Soil": ".", "SoilRich": "*", "Gravel": ",", "Mud": "~", "WaterShallow": "w", "Sandstone_Rough": "s",
      "Sandstone_RoughHewn": "s", "Limestone_Rough": "l", "Marble_Rough": "m", "Marble_RoughHewn": "m",
      "AncientConcrete": "t", "AncientTile": "t", "TileMarble": "t", "FlagstoneSandstone": "t", "BrokenAsphalt": "t"}
tc = {"Limestone": "L", "Sandstone": "S", "Marble": "M", "MineableSteel": "$", "MineableComponentsIndustrial": "C",
      "MineableSilver": "A", "MineableGold": "G", "MineableUranium": "U", "MineableJade": "J",
      "ChunkLimestone": "o", "ChunkMarble": "o", "ChunkSandstone": "o", "ChunkSlagSteel": "o"}
terr, rf = [], []
for z in range(N):
    terr.append("".join(tc.get(TH.get(th[z, x])) or gc.get(T.get(top[z, x]), ".") for x in range(N)))
    rf.append("".join({"Thick": "1", "Constructed": "2", "Thin": "3"}.get(R.get(roof[z, x]), "0") for x in range(N)))
rows = pickle.load(open(things_pkl, "rb"))

def P(s):
    a = re.findall(r"-?\d+", s)
    return int(a[0]), int(a[2])

existing = []
for r in rows:
    if r["fac"] == "Faction_152" and r["cls"] != "Pawn" and r["pos"]:
        x, z = P(r["pos"])
        existing.append([x, z, r["def_"]])
FEAT = {"SteamGeyser": "증기 분출구", "VoidMonolith": "공허 모노리스", "Hive": "곤충 둥지", "Plant_TreeAnima": "영혼나무",
        "AncientCryptosleepCasket": "고대 동면관", "Sarcophagus": "석관", "AncientMechDropBeacon": "고대 메카 투하 신호기",
        "AncientHermeticCrate": "고대 밀폐 상자"}
features = []
for r in rows:
    if r["def_"] in FEAT and r["pos"]:
        x, z = P(r["pos"])
        features.append([x, z, FEAT[r["def_"]]])
colonists = []
for r in rows:
    if r["def_"] == "Human" and r["fac"] == "Faction_152":
        x, z = P(r["pos"])
        colonists.append([x, z])
bp = json.load(open(layout))
json.dump(dict(n=N, terrain=terr, roof=rf, existing=existing, features=features, colonists=colonists, layout=bp),
          open(out, "w"), ensure_ascii=False, separators=(",", ":"))
print("ok", out)
