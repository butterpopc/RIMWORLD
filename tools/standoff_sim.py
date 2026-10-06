# -*- coding: utf-8 -*-
"""킬존 사선 분석: 적이 '사로에 나오지 않고' 사대를 쏠 수 있는 자리가 있는지, 사로에서 적이 얻는 엄폐는 얼마인지.

사용: python3 -I tools/standoff_sim.py <arr.pkl> <layout.json> [out.json]

디컴파일 1.6 규칙을 옮김(요약):
  GenSight.LineOfSight      : 정수 격자 걷기, 시작 칸 제외, 벽·닫힌 문에서 차단
  ShootLeanUtility          : 벽에 붙은 폰은 옆 칸(동서남북)에서 쏘거나 맞을 수 있음(몸 내밀기)
  Verb 사선 판정            : (사수의 내밀기 칸들) × (표적의 내밀기 칸들) 중 하나라도 시야가 통하면 사격 가능
  CoverUtility              : 표적 주변 8칸의 엄폐물마다 각도 차이로 감쇠(15/27/40/52/65°, 대각 ×1.75), 사수가 엄폐물에 가까우면 감쇠
가정: 모래주머니·바리케이드 엄폐율 0.55 [XML·확인 필요], 문은 닫힘, 무기 사거리 제한 없음(최악).
"""
import json, math, pickle, sys

N = 275
arr_pkl, layout = sys.argv[1:3]
out = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("{") else None
VAR = json.loads(sys.argv[-1]) if sys.argv[-1].startswith("{") else {}   # 변형: {"walls":[[x,z]..], "sandbags":[[x,z]..], "shooters":[[x,z]..]}
D = pickle.load(open(arr_pkl, "rb"))
th, TH = D["th"], D["TH"]
bp = json.load(open(layout))
ROCK = {"Limestone", "Sandstone", "Marble"}
LOW_COVER = 0.55

def cells(r):
    for z in range(r[1], r[3] + 1):
        for x in range(r[0], r[2] + 1):
            yield x, z

def is_rock(x, z):
    t = TH.get(th[z, x])
    return bool(t) and (t in ROCK or t.startswith("Mineable"))

# 0 열림, 1 막힘(시야 차단·엄폐 0.75), 2 낮은 엄폐(시야 통과)
G = [[1 if is_rock(x, z) else 0 for x in range(N)] for z in range(N)]
owner = {}
for s in bp["spaces"]:
    for c in cells(s["rect"]):
        G[c[1]][c[0]] = 0; owner[c] = s["id"]
for f in bp["fill"]:
    for c in cells(f["rect"]):
        G[c[1]][c[0]] = 1
for x, z in bp["coolers"] + bp["doors"]:
    G[z][x] = 1
SB = [tuple(c) for c in VAR["sandbags"]] if "sandbags" in VAR else list(cells(bp["sandbags"]))
for x, z in SB + [tuple(b) for b in bp.get("barricades", [])]:
    G[z][x] = 2
for x, z in VAR.get("walls", []):
    G[z][x] = 1

ADJ = [(0, 1), (1, 0), (0, -1), (-1, 0), (1, -1), (1, 1), (-1, 1), (-1, -1)]   # GenAdj.AdjacentCells 순서

def see_over(x, z):
    return G[z][x] != 1

def angle_flat(dx, dz):
    if dx == 0 and dz == 0:
        return 0.0
    return math.degrees(math.atan2(dx, dz)) % 360

def los(a, b):
    (x0, z0), (x1, z1) = a, b
    flag = (x0 < x1) if x0 != x1 else (z0 < z1)
    nx, nz = abs(x1 - x0), abs(z1 - z0)
    x, z = x0, z0
    n = 1 + nx + nz
    sx = 1 if x1 > x0 else -1
    sz = 1 if z1 > z0 else -1
    nx *= 4; nz *= 4
    err = nx // 2 - nz // 2
    while n > 1:
        if (x, z) != (x0, z0) and not see_over(x, z):
            return False
        if err > 0 or (err == 0 and flag):
            x += sx; err -= nz
        else:
            z += sz; err += nx
        n -= 1
    return True

def lean_sources(loc, target):
    ang = angle_flat(target[0] - loc[0], target[1] - loc[1])
    f1 = ang > 270 or ang < 90
    f2 = 90 < ang < 270
    f3 = ang > 180
    f4 = ang < 180
    b = [not see_over(loc[0] + dx, loc[1] + dz) for dx, dz in ADJ]
    res = []
    E, Wd, S, Nn = (loc[0] + 1, loc[1]), (loc[0] - 1, loc[1]), (loc[0], loc[1] - 1), (loc[0], loc[1] + 1)
    if not b[1] and ((b[0] and not b[5] and f1) or (b[2] and not b[4] and f2)): res.append(E)
    if not b[3] and ((b[0] and not b[6] and f1) or (b[2] and not b[7] and f2)): res.append(Wd)
    if not b[2] and ((b[3] and not b[7] and f3) or (b[1] and not b[4] and f4)): res.append(S)
    if not b[0] and ((b[3] and not b[6] and f3) or (b[1] and not b[5] and f4)): res.append(Nn)
    if see_over(*loc): res.append(loc)
    return res

def can_hit(shooter, target):
    for s in lean_sources(shooter, target):
        for t in lean_sources(target, shooter):
            if los(s, t):
                return True
    return False

def block_chance(target, shooter):
    tot = 0.0
    for dx, dz in ADJ:
        c = (target[0] + dx, target[1] + dz)
        if c == shooter or G[c[1]][c[0]] == 0:
            continue
        base = 0.75 if G[c[1]][c[0]] == 1 else LOW_COVER
        diff = abs((angle_flat(dx, dz) - angle_flat(shooter[0] - target[0], shooter[1] - target[1]) + 180) % 360 - 180)
        if dx and dz:
            diff *= 1.75
        if diff < 15: f = 1
        elif diff < 27: f = 0.8
        elif diff < 40: f = 0.6
        elif diff < 52: f = 0.4
        elif diff < 65: f = 0.2
        else: continue
        d = math.hypot(shooter[0] - c[0], shooter[1] - c[1])
        if d < 1.9: f *= 0.3333
        elif d < 2.9: f *= 0.66666
        tot += (1 - tot) * base * f
    return tot

fl = [tuple(c) for c in VAR["shooters"]] if "shooters" in VAR else [c for c in cells(bp["killzone"]["firing_line"]) if G[c[1]][c[0]] == 0]
maze = [c for c, o in owner.items() if o.startswith("MZ") and G[c[1]][c[0]] == 0]
lane = [c for c, o in owner.items() if o == "LR" and c[0] > bp["sandbags"][0]]

snipe = []
for m in maze:
    hits = [f for f in fl if can_hit(m, f)]
    if hits:
        back = [f for f in fl if can_hit(f, m)]
        snipe.append(dict(cell=m, space=owner[m], can_hit_fl=len(hits), fl_can_hit_back=len(back)))
lane_stats = []
for c in lane:
    back = [f for f in fl if can_hit(f, c)]
    cov = [block_chance(c, f) for f in back] or [0]
    lane_stats.append(dict(cell=c, fl_can_hit=len(back), cover_avg=sum(cov) / len(cov), cover_max=max(cov)))
covered = [s for s in lane_stats if s["cover_avg"] >= 0.2]
print(f"사대 칸 {len(fl)} / 미로 칸 {len(maze)} / 사로 칸 {len(lane)}")
print(f"[A] 사로에 나오지 않고 사대를 쏠 수 있는 미로 칸: {len(snipe)}개")
for s in snipe:
    print(f"    {s['cell']} {s['space']}: 사대 {s['can_hit_fl']}칸을 쏠 수 있음, 되쏠 수 있는 사대 칸 {s['fl_can_hit_back']}/{len(fl)}")
mn = min(s["fl_can_hit"] for s in lane_stats)
print(f"[B] 사로 칸을 쏠 수 있는 사대 칸 수: 최소 {mn}/{len(fl)}, 평균 {sum(s['fl_can_hit'] for s in lane_stats)/len(lane_stats):.1f}")
print(f"[C] 사로에서 적이 얻는 평균 엄폐율: 전체 평균 {100*sum(s['cover_avg'] for s in lane_stats)/len(lane_stats):.1f}%, "
      f"20% 이상인 칸 {len(covered)}개 {[s['cell'] for s in covered][:10]}")
# [D] 아군 사수가 받는 엄폐: 사수 칸마다, 그 사수를 쏠 수 있는 사로 칸들에서 본 평균 엄폐율
dstats = []
for f in fl:
    att = [c for c in lane if can_hit(c, f)]
    cov = [block_chance(f, c) for c in att] or [0]
    hit = [c for c in lane if can_hit(f, c)]
    dstats.append((f, len(hit), len(att), sum(cov) / len(cov)))
print(f"[D] 사수 칸 {len(fl)}개: 사로 사격 가능 평균 {sum(d[1] for d in dstats)/len(dstats):.0f}/{len(lane)}칸, "
      f"사수가 받는 평균 엄폐 {100*sum(d[3] for d in dstats)/len(dstats):.0f}% (최소 {100*min(d[3] for d in dstats):.0f}%)")
for d in dstats[:7]:
    print(f"    {d[0]}: 사로 {d[1]}칸 사격 가능, {d[2]}칸에서 피격 가능, 엄폐 {100*d[3]:.0f}%")
if out:
    json.dump(dict(snipe=snipe, lane=lane_stats), open(out, "w"), ensure_ascii=False, indent=1)
