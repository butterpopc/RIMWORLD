# -*- coding: utf-8 -*-
"""돌파·공병 습격 경로 모의 실험 (디컴파일한 1.6 비용식 근사).

사용: python3 -I tools/raid_sim.py <arr.pkl> <things.pkl> <layout_v3.json> [out.json]

근거(디컴파일 소스, 요약):
  - GenAI.RandomRaidDest: 돌파·공병 목적지 = 주인 있는 침대 중 무작위
  - PathGridJob.CostForCell: 부술 칸 = 70 + 0.2*HP, 회피격자 값*8 가산
  - AvoidGrid: 플레이어 포탑(전원 무관) 사거리+4 안에서 포탑이 보이는 걷기 가능 칸마다 +45
  - PathFinderCostTuning: 문 = 50 + 0.2*HP
근사: 이동 비용 직선 13 / 대각 18, 바리케이드 +42, 대각선은 양옆 직교 칸이 모두 통행 가능할 때만.
"""
import heapq, json, math, pickle, sys

N = 275
arr_pkl, things_pkl, layout = sys.argv[1:4]
out = sys.argv[4] if len(sys.argv) > 4 else None
D = pickle.load(open(arr_pkl, "rb"))
top, roof, th, T, TH, R = [D[k] for k in "top roof th T TH R".split()]
bp = json.load(open(layout))
ROCK = {"Limestone", "Sandstone", "Marble"}

def is_rock(x, z):
    t = TH.get(th[z, x])
    return bool(t) and (t in ROCK or t.startswith("Mineable"))

def cells(r):
    for z in range(r[1], r[3] + 1):
        for x in range(r[0], r[2] + 1):
            yield x, z

# 0 open, 1 rock, 2 constructed wall, 3 door
G = [[1 if is_rock(x, z) else 0 for x in range(N)] for z in range(N)]
owner = {}
for s in bp["spaces"]:
    for c in cells(s["rect"]):
        G[c[1]][c[0]] = 0
        owner[c] = s["id"]
for f in bp["fill"]:
    for c in cells(f["rect"]):
        G[c[1]][c[0]] = 2
for x, z in bp["coolers"] + [tuple(c) for c in bp.get("fl_walls", [])]:
    G[z][x] = 2
for x, z in bp["doors"]:
    G[z][x] = 3
EXTRA = {}
for x, z in bp.get("barricades", []):
    EXTRA[(x, z)] = 42
for x, z in list(cells(bp["sandbags"])):
    EXTRA[(x, z)] = 42
KZ = set(bp["killzone"]["ids"])
MAZE_MOUTH = tuple(bp["spaces"][[s["id"] for s in bp["spaces"]].index("MZT")]["rect"][:2])
beds = [s["id"] for s in bp["spaces"] if s["id"][0] == "B" and s["id"][1:].isdigit()] + ["BC", "PRIS"]
bed_cells = {b: next(((s["rect"][0] + s["rect"][2]) // 2, (s["rect"][1] + s["rect"][3]) // 2)
                     for s in bp["spaces"] if s["id"] == b) for b in beds}

def los(a, b):
    (x0, z0), (x1, z1) = a, b
    n = max(abs(x1 - x0), abs(z1 - z0))
    for i in range(1, n):
        x = round(x0 + (x1 - x0) * i / n); z = round(z0 + (z1 - z0) * i / n)
        if G[z][x] != 0:
            return False
    return True

def avoid_grid(turrets, rng=28.9, min_rng=0.0):
    A = {}
    r = rng + 4
    for tx, tz in turrets:
        for z in range(max(0, int(tz - r)), min(N, int(tz + r) + 1)):
            for x in range(max(0, int(tx - r)), min(N, int(tx + r) + 1)):
                d2 = (x - tx) ** 2 + (z - tz) ** 2
                if min_rng * min_rng <= d2 <= r * r and G[z][x] == 0 and los((x, z), (tx, tz)):
                    A[(x, z)] = min(255, A.get((x, z), 0) + 45)
    return A

def run(rock_hp, wall_hp, door_hp, avoid, starts):
    rock_c = 70 + 0.2 * rock_hp
    wall_c = 70 + 0.2 * wall_hp
    door_c = 50 + 0.2 * door_hp
    def cell_cost(x, z):
        g = G[z][x]
        c = rock_c if g == 1 else wall_c if g == 2 else door_c if g == 3 else 0
        c += EXTRA.get((x, z), 0)
        c += avoid.get((x, z), 0) * 8
        return c
    results = []
    for sx, sz in starts:
        dist = {(sx, sz): 0}
        prev = {}
        pq = [(0, sx, sz)]
        targets = set(bed_cells.values())
        found = {}
        while pq and len(found) < len(targets):
            d, x, z = heapq.heappop(pq)
            if d > dist.get((x, z), 1e18):
                continue
            if (x, z) in targets:
                found[(x, z)] = d
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    if not dx and not dz:
                        continue
                    nx, nz = x + dx, z + dz
                    if not (0 <= nx < N and 0 <= nz < N):
                        continue
                    if dx and dz and (G[z][nx] != 0 or G[nz][x] != 0):
                        continue
                    nd = d + (18 if dx and dz else 13) + cell_cost(nx, nz)
                    if nd < dist.get((nx, nz), 1e18):
                        dist[(nx, nz)] = nd; prev[(nx, nz)] = (x, z)
                        heapq.heappush(pq, (nd, nx, nz))
        for b, bc in bed_cells.items():
            if bc not in found:
                continue
            path, c = [], bc
            while c != (sx, sz):
                path.append(c); c = prev[c]
            path.reverse()
            via_kz = any(owner.get(p) == "LR" for p in path)   # 사로를 지나면 킬존 경유(미로 벽을 파고 들어와도 결국 사로로 나옴)
            dug = [p for p in path if G[p[1]][p[0]] in (1, 2)]
            first_room = None
            if dug:
                # 처음 뚫고 들어간 공간
                for p in path[path.index(dug[0]):]:
                    if owner.get(p):
                        first_room = owner[p]; break
            results.append(dict(start=(sx, sz), bed=b, via_killzone=via_kz, dug_cells=len(dug),
                                breach_into=first_room, cost=round(found[bc])))
    return results

# 습격 시작점: 지도 가장자리 중 바깥 통행 가능 칸 (남·동·서 가장자리 표본)
starts = []
for x in range(10, N - 10, 30):
    if G[0][x] == 0: starts.append((x, 0))
for z in range(10, 200, 30):
    if G[z][0] == 0: starts.append((0, z))
    if G[z][N - 1] == 0: starts.append((N - 1, z))

TURRETS_FL = [(152, 176), (152, 182)]           # 시험용: 사대 모서리 포탑 2기
DECOY = [(184, 166)]                             # 시험용: 미로 입구 앞 전원 끈 포탑
MORTARS = [tuple(p["xz"]) for p in bp["points"] if "박격포" in p["name"]]
scen = []
for rock_hp in (600, 1000, 1500):
    for label, turrets in (("포탑 없음", []), ("사대 포탑 2", TURRETS_FL), ("미끼 포탑 1", DECOY), ("사대 2 + 미끼 1", TURRETS_FL + DECOY)):
        for smart in (False, True):
            if not smart and turrets:
                continue  # 일반 돌파는 회피격자 미사용 → 포탑 유무와 무관
            A = avoid_grid(turrets) if smart else {}
            res = run(rock_hp, wall_hp=360, door_hp=250, avoid=A, starts=starts)
            n = len(res)
            kz = sum(r["via_killzone"] for r in res)
            into = {}
            for r in res:
                if not r["via_killzone"]:
                    into[r["breach_into"]] = into.get(r["breach_into"], 0) + 1
            scen.append(dict(rock_hp=rock_hp, turrets=label, smart=smart, pairs=n, via_killzone=kz,
                             pct=round(100 * kz / n) if n else None, breach_into=into))
            print(f"암반HP {rock_hp:4d} | {label:10s} | {'똑똑함' if smart else '일반  '} | 킬존 경유 {kz}/{n} ({round(100*kz/n) if n else '-'}%) | 우회 굴착 진입: {into}")
# 드롭포드: 두꺼운 지붕 밖 산 앞 빈터에 착륙한 경우(포탑 없음)
POD_STARTS = [(115, 162), (135, 164), (150, 160), (165, 160), (178, 162), (190, 162), (200, 150), (140, 140)]
POD_STARTS = [p for p in POD_STARTS if G[p[1]][p[0]] == 0 and R.get(roof[p[1], p[0]]) != "Thick"]
for rock_hp in (600, 1000, 1500):
    res = run(rock_hp, wall_hp=360, door_hp=250, avoid={}, starts=POD_STARTS)
    kz = sum(r["via_killzone"] for r in res)
    into = {}
    for r in res:
        if not r["via_killzone"]:
            into[r["breach_into"]] = into.get(r["breach_into"], 0) + 1
    scen.append(dict(rock_hp=rock_hp, turrets="포탑 없음(드롭포드 착륙점)", smart=True, pairs=len(res), via_killzone=kz,
                     pct=round(100 * kz / len(res)), breach_into=into))
    print(f"암반HP {rock_hp:4d} | 드롭포드 착륙점 {len(POD_STARTS)}곳 | 포탑 없음 | 킬존 경유 {kz}/{len(res)} ({round(100*kz/len(res))}%) | 우회 굴착 진입: {into}")
# 박격포가 회피 격자를 만든다고 가정한 최악의 경우(사거리 120으로 근사, 최소 사거리 29.9)
for rock_hp in (1000,):
    A = avoid_grid(MORTARS, rng=120, min_rng=29.9)
    res = run(rock_hp, wall_hp=360, door_hp=250, avoid=A, starts=starts)
    kz = sum(r["via_killzone"] for r in res)
    into = {}
    for r in res:
        if not r["via_killzone"]:
            into[r["breach_into"]] = into.get(r["breach_into"], 0) + 1
    scen.append(dict(rock_hp=rock_hp, turrets="박격포 2(가정)", smart=True, pairs=len(res), via_killzone=kz,
                     pct=round(100 * kz / len(res)), breach_into=into))
    print(f"암반HP {rock_hp:4d} | 박격포 2(가정) | 똑똑함 | 킬존 경유 {kz}/{len(res)} ({round(100*kz/len(res))}%) | 우회 굴착 진입: {into}")
if out:
    json.dump(dict(starts=starts, scenarios=scen), open(out, "w"), ensure_ascii=False, indent=1)
