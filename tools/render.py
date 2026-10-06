# -*- coding: utf-8 -*-
"""layout_v3.json 을 실제 지형 위에 PNG로 렌더링.
사용: python3 -I tools/render.py <arr.pkl> <layout_v3.json> <out.png> x0 z0 x1 z1 scale
"""
import json, pickle, sys
from PIL import Image, ImageDraw, ImageFont

arr_pkl, layout, out = sys.argv[1:4]
x0, z0, x1, z1, S = map(int, sys.argv[4:9])
D = pickle.load(open(arr_pkl, "rb"))
top, roof, th, T, TH, R = [D[k] for k in "top roof th T TH R".split()]
bp = json.load(open(layout))
try:
    FONT = ImageFont.truetype("/usr/share/fonts/opentype/unifont/unifont.otf", 16)
except OSError:
    FONT = ImageFont.load_default()

GROUND = {"Soil": (112, 138, 74), "SoilRich": (70, 112, 50), "Gravel": (160, 155, 138), "Mud": (110, 92, 64),
          "WaterShallow": (70, 125, 205)}
ROCK = {"Limestone": (118, 113, 92), "Sandstone": (128, 88, 60), "Marble": (150, 150, 162)}
ORE = {"MineableSteel": (205, 70, 70), "MineableComponentsIndustrial": (235, 195, 30), "MineableSilver": (140, 210, 240),
       "MineableGold": (240, 160, 20), "MineableUranium": (60, 220, 110), "MineableJade": (40, 150, 110)}
# 기능군 색: 방어 / 식량 / 생활 / 생산 / 의료·수감 / 전력 / 통로 / 특수
GROUP = {"LR": "def", "V": "def", "WR": "def", "MZT": "def", "MZA": "def", "MZ1": "def", "MZB": "def", "MZ2": "def", "MZC": "def", "MZD": "def", "MZE": "def", "MZM": "def", "BTA": "def", "BTB": "def", "BTT": "def", "ER": "med", "FRZ": "food", "KIT": "food", "HYD1": "food",
         "HYD2": "food", "HALL": "life", "BC": "life", "PRIS": "med", "WS": "prod", "STO": "prod",
         "LAB": "prod", "MECH": "prod", "BAT": "power", "CONT": "special"}
GCOL = {"def": (205, 70, 60), "food": (95, 175, 225), "life": (235, 205, 120), "med": (120, 205, 150),
        "prod": (200, 150, 105), "power": (245, 225, 70), "special": (160, 80, 175), "corr": (225, 225, 220),
        "bed": (240, 185, 205)}
OUTC = {"F1": (150, 200, 80), "F2": (170, 210, 100), "OLD": (200, 200, 200), "SOL": (80, 120, 220),
        "WIND": (120, 200, 230), "APRON": (220, 80, 80), "GRAVE": (120, 120, 120), "PAD": (200, 200, 255),
        "FISH": (60, 140, 230)}

W, H = (x1 - x0 + 1) * S, (z1 - z0 + 1) * S
img = Image.new("RGB", (W, H))
d = ImageDraw.Draw(img, "RGBA")

def px(x, z):
    return (x - x0) * S, (z1 - z) * S

for z in range(z0, z1 + 1):
    for x in range(x0, x1 + 1):
        t = TH.get(th[z, x])
        c = ORE.get(t) or ROCK.get(t) or GROUND.get(T.get(top[z, x]), (175, 165, 140))
        if R.get(roof[z, x]) == "Thick" and t in ROCK:
            c = tuple(int(v * 0.6) for v in c)
        X, Y = px(x, z)
        d.rectangle([X, Y, X + S - 1, Y + S - 1], fill=c)

def rect(r, fill, outline=None, width=1):
    a, b, c, e = r
    X0, Y0 = px(a, e)
    X1, Y1 = px(c, b)
    d.rectangle([X0, Y0, X1 + S - 1, Y1 + S - 1], fill=fill, outline=outline, width=width)

def cell(x, z, fill, inset=0):
    X, Y = px(x, z)
    d.rectangle([X + inset, Y + inset, X + S - 1 - inset, Y + S - 1 - inset], fill=fill)

for o in bp["outdoor"]:
    col = OUTC.get(o["id"], (255, 255, 255))
    rect(o["rect"], col + (70,), col + (255,), 2)
for s in bp["spaces"]:
    g = GROUP.get(s["id"]) or ("bed" if s["id"].startswith("B") else "corr")
    rect(s["rect"], GCOL[g] + (220,), (25, 25, 25, 255), 1)
for f in bp["fill"]:
    rect(f["rect"], (45, 45, 45, 255))
rect(bp["sandbags"], (150, 115, 60, 255))
for x, z in bp["doors"]:
    cell(x, z, (125, 75, 25, 255))
for x, z in bp["firedoors"]:
    cell(x, z, (230, 90, 30, 255), max(1, S // 5))
for x, z in bp["coolers"]:
    cell(x, z, (0, 200, 255, 255))
for x, z in bp.get("fl_walls", []):
    cell(x, z, (45, 45, 45, 255))
for x, z in bp["turrets"]:
    cell(x, z, (255, 30, 30, 255))
for x, z in bp.get("bait_turret", []):
    cell(x, z, (120, 120, 120, 255), max(1, S // 6))   # 꺼진 포탑(벽장)
for x, z in bp.get("barricades", []):
    cell(x, z, (150, 115, 60, 255), max(1, S // 4))
for x, z in bp.get("melee_spots", []):
    cell(x, z, (255, 255, 255, 255), max(1, S // 3))
for x, z in bp.get("bait", []):
    cell(x, z, (190, 140, 255, 255))
for x, z in bp["sunlamps"]:
    cell(x, z, (255, 255, 140, 255))
pts = bp["conduit"]
for (ax, az), (bx, bz) in zip(pts, pts[1:]):
    A, B = px(ax, az), px(bx, bz)
    d.line([(A[0] + S // 2, A[1] + S // 2), (B[0] + S // 2, B[1] + S // 2)], fill=(255, 225, 0, 230), width=max(2, S // 3))
for p in bp["points"] + bp["tempgen"]:
    x, z = p["xz"]
    X, Y = px(x, z)
    d.ellipse([X - 2, Y - 2, X + S + 1, Y + S + 1], fill=(255, 140, 0, 255), outline=(0, 0, 0, 255))

def label(r, text):
    a, b, c, e = r
    if not (x0 <= a and c <= x1 and z0 <= b and e <= z1):
        return
    X0, Y0 = px(a, e)
    X1, Y1 = px(c, b)
    cx, cy = (X0 + X1 + S) // 2, (Y0 + Y1 + S) // 2
    bb = d.textbbox((0, 0), text, font=FONT)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    d.rectangle([cx - w // 2 - 2, cy - h // 2 - 2, cx + w // 2 + 2, cy + h // 2 + 2], fill=(0, 0, 0, 160))
    d.text((cx - w // 2, cy - h // 2 - 1), text, font=FONT, fill=(255, 255, 255))

for s in bp["spaces"]:
    if s["kind"] == "room":
        label(s["rect"], s["id"])
for o in bp["outdoor"]:
    label(o["rect"], o["id"])
for i in range(0, 275, 5):
    if x0 <= i <= x1:
        X, _ = px(i, z1)
        d.line([(X, 0), (X, H)], fill=(0, 0, 0, 55 if i % 10 else 120))
        if i % 10 == 0:
            d.text((X + 2, 2), str(i), font=FONT, fill=(255, 255, 255))
    if z0 <= i <= z1:
        _, Y = px(x0, i)
        d.line([(0, Y + S), (W, Y + S)], fill=(0, 0, 0, 55 if i % 10 else 120))
        if i % 10 == 0:
            d.text((2, Y - 16), str(i), font=FONT, fill=(255, 255, 255))
img.save(out)
print("saved", out, img.size)
