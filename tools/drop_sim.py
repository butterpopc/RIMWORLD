# -*- coding: utf-8 -*-
"""드롭포드(중앙 투하) 착륙 가능성 분석 — 디컴파일한 1.6 규칙 근사.

사용: python3 -I tools/drop_sim.py <arr.pkl> <layout_v3.json> [out.json]

근거(디컴파일 소스, 요약):
  PawnsArrivalModeWorker_CenterDrop.TryResolveRaidSpawnCenter
    - 메카노이드가 아니고 궤도 무역 신호기가 있으면 40% 확률로 DropCellFinder.TradeDropSpot
    - 아니면 DropCellFinder.TryFindRaidDropCenterClose(canRoofPunch = 인간 적대, allowIndoors = 메카 아님)
      실패하면 EdgeDrop(멀리 떨어진 곳)으로 전환
  DropCellFinder.TryFindRaidDropCenterClose
    - 무작위 정착민 위치 → CellFinder.RandomClosewalkCellNear(반경 10):
      닫힌 문을 지나지 않고 이어진 영역 안, 직선거리 10 이내의 서 있을 수 있는 칸 하나를 무작위로 고름
    - 그 칸이 CanPhysicallyDropInto면 채택, 아니면 300회까지 재시도
  DropCellFinder.CanPhysicallyDropInto
    - 걷기 가능, 물 아님, 지붕이 있으면 지붕 뚫기 허용일 때만, **두꺼운 지붕은 불가**
  DropCellFinder.TradeDropSpot
    - 지붕 없는 신호기(+인접 착륙 가능 칸)가 있으면 그 근처
    - 없으면 전원 켜진 신호기·통신 콘솔 주변 반경 8부터 ×1.1씩 넓혀 지붕 없는 착륙 칸을 무작위로
"""
import collections, json, math, pickle, sys

N = 275
arr_pkl, layout = sys.argv[1:3]
out = sys.argv[3] if len(sys.argv) > 3 else None
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

# 격자: 0 통행, 1 막힘(암반·벽), 3 문(닫힘 = 영역 경계)
G = [[1 if is_rock(x, z) else 0 for x in range(N)] for z in range(N)]
owner = {}
for s in bp["spaces"]:
    for c in cells(s["rect"]):
        G[c[1]][c[0]] = 0; owner[c] = s["id"]
for f in bp["fill"]:
    for c in cells(f["rect"]):
        G[c[1]][c[0]] = 1
for x, z in bp["coolers"]:
    G[z][x] = 1
for x, z in bp["doors"]:
    G[z][x] = 3
water = {(x, z) for z in range(N) for x in range(N) if T.get(top[z, x]) == "WaterShallow"}

def roof_of(x, z):
    return R.get(roof[z, x])

def can_drop(x, z, roof_punch, allow_indoors=True):
    if G[z][x] != 0 or (x, z) in water:
        return False
    rf = roof_of(x, z)
    if rf:
        if not roof_punch or rf == "Thick":
            return False
    if not allow_indoors and (x, z) in owner:   # 근사: 설계 공간 = 실내
        return False
    return True

def closewalk(root, radius=10):
    """닫힌 문을 지나지 않고 이어진, 직선거리 radius 이내 칸(근사: 4방향 BFS)."""
    rx, rz = root
    seen = {root}
    q = collections.deque([root])
    r2 = radius * radius
    while q:
        x, z = q.popleft()
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, z + dz)
            if 0 <= n[0] < N and 0 <= n[1] < N and n not in seen and G[n[1]][n[0]] == 0 \
                    and (n[0] - rx) ** 2 + (n[1] - rz) ** 2 <= r2:
                seen.add(n); q.append(n)
    return seen

def exposure(c, roof_punch=True, allow_indoors=True):
    near = closewalk(c)
    ok = [d for d in near if can_drop(*d, roof_punch, allow_indoors)]
    return len(ok), len(near)

report = collections.OrderedDict()
# 1) 설계 공간별 노출: 그 공간에 정착민이 서 있을 때 근처(반경 10)에 투하 가능한 칸이 있는가
for s in bp["spaces"]:
    exp_h = exp_m = 0
    n = 0
    for c in cells(s["rect"]):
        if G[c[1]][c[0]] != 0:
            continue
        n += 1
        a, _ = exposure(c, roof_punch=True, allow_indoors=True)
        b, _ = exposure(c, roof_punch=False, allow_indoors=False)
        exp_h += a > 0; exp_m += b > 0
    report[s["id"]] = dict(name=s["name"], cells=n, exposed_human=exp_h, exposed_mech=exp_m)

# 2) 사대·대기실에서 투하 가능한 가장 가까운 칸까지 보행 거리
def walk_dist_to_drop(srcs, roof_punch=True):
    dist = {c: 0 for c in srcs}
    q = collections.deque(srcs)
    while q:
        x, z = q.popleft()
        if can_drop(x, z, roof_punch) and dist[(x, z)] > 0:
            return dist[(x, z)], (x, z)
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, z + dz)
            if 0 <= n[0] < N and 0 <= n[1] < N and n not in dist and G[n[1]][n[0]] in (0, 3):
                dist[n] = dist[(x, z)] + 1; q.append(n)
    return None, None
fl = list(cells(bp["killzone"]["firing_line"]))
d_fl, c_fl = walk_dist_to_drop(fl)
wr = [c for c, o in owner.items() if o == "WR"]
d_wr, c_wr = walk_dist_to_drop(wr)

# 3) 무역 투하 지점: 신호기(창고) + 통신 콘솔(연구실), 둘 다 두꺼운 지붕 아래 → 반경 확장 탐색
def trade_drop_zone(buildings):
    r = 8
    while r <= N:
        zone = set()
        for bx, bz in buildings:
            for z in range(max(0, bz - r), min(N, bz + r + 1)):
                for x in range(max(0, bx - r), min(N, bx + r + 1)):
                    if (x - bx) ** 2 + (z - bz) ** 2 <= r * r and can_drop(x, z, roof_punch=False):
                        zone.add((x, z))
        if zone:
            return r, sorted(zone)
        r = round(r * 1.1)
    return None, []
def center(sid):
    s = next(s for s in bp["spaces"] if s["id"] == sid)
    a, b, c, d = s["rect"]
    return ((a + c) // 2, (b + d) // 2)
beacon, console = center("STO"), center("LAB")
r_trade, zone_trade = trade_drop_zone([beacon, console])

# 4) 바깥 작업 지점에서 대기실까지 보행 거리(문 통과 허용) — 투하 시 대피 거리
def walk(a, b):
    dist = {a: 0}
    q = collections.deque([a])
    while q:
        x, z = q.popleft()
        if (x, z) == b:
            return dist[b]
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, z + dz)
            if 0 <= n[0] < N and 0 <= n[1] < N and n not in dist and G[n[1]][n[0]] in (0, 3):
                dist[n] = dist[(x, z)] + 1; q.append(n)
    return None
wr_c = center("WR")
work = {o["id"]: ((o["rect"][0] + o["rect"][2]) // 2, (o["rect"][1] + o["rect"][3]) // 2) for o in bp["outdoor"]}
evac = {k: walk(v, wr_c) for k, v in work.items()}
mouth = (bp["spaces"][[s["id"] for s in bp["spaces"]].index("MZT")]["rect"][0], 167)
evac_mouth = {k: walk(v, mouth) for k, v in work.items()}

print("== 1) 정착민이 서 있으면 중앙 투하 표적이 될 수 있는 칸 (인간: 지붕 뚫기 / 메카: 실외만) ==")
for k, v in report.items():
    if v["exposed_human"] or v["exposed_mech"]:
        print(f"  {k:5s} {v['name']}: 인간 {v['exposed_human']}/{v['cells']}칸, 메카 {v['exposed_mech']}/{v['cells']}칸")
safe = [k for k, v in report.items() if not v["exposed_human"] and not v["exposed_mech"]]
print(f"  노출 0인 공간 {len(safe)}/{len(report)}: 킬존 사로·사대·전실·대기실·응급실 포함 여부 =",
      all(s in safe for s in ("LR", "V", "WR", "ER")))
print(f"== 2) 투하 가능한 가장 가까운 칸까지 보행 거리: 사대 {d_fl}칸 {c_fl}, 대기실 {d_wr}칸 {c_wr} (중앙 투하 반경 10) ==")
xs = [c[0] for c in zone_trade]; zs = [c[1] for c in zone_trade]
print(f"== 3) 무역 투하 지점: 반경 {r_trade}에서 처음 성립, 후보 {len(zone_trade)}칸, 범위 x{min(xs)}~{max(xs)} z{min(zs)}~{max(zs)} ==")
print("== 4) 바깥 시설 → 대기실 보행 거리 / → 미로 입구 ==")
for k in work:
    print(f"  {k}: {evac[k]} / {evac_mouth[k]}")
if out:
    json.dump(dict(spaces=report, fl_min_walk_to_drop=d_fl, wr_min_walk_to_drop=d_wr,
                   trade_drop=dict(radius=r_trade, cells=len(zone_trade), bbox=[min(xs), min(zs), max(xs), max(zs)]),
                   evac_to_wr=evac, evac_to_mouth=evac_mouth), open(out, "w"), ensure_ascii=False, indent=1)
