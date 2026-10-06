# -*- coding: utf-8 -*-
"""적의 '전투 상태(anyCloseHostilesRecently)'가 켜지는 위치 분석 — 1명씩 순차 입장(폰 충돌)의 전제 조건.

사용: python3 -I tools/region_sim.py <arr.pkl> <layout_v3.json> [out.json]

디컴파일 1.6 코드(요약):
  Pawn_MindState: 100틱마다 anyCloseHostilesRecently = EnemiesAreNearby(pawn, 꺼져 있으면 18 / 켜져 있으면 24 지역, passDoors=true)
  PawnUtility.EnemiesAreNearby: 지역(region) 너비우선 탐색, 문 통과, 지역 안 'AttackTarget' 무리의 적대 사물이 1개라도 있으면 참.
                                전원·위협 여부를 보지 않는다 → 꺼진 포탑·닫힌 문 뒤 포탑도 센다
  RegionMaker / Region.MakeNewUnfilled: 지역 = 12×12 구획 안에서 같은 종류로 이어진 칸. 문 칸은 따로 '문 지역'
  RegionTraverser.ShouldCountRegion: 문 지역은 개수에 넣지 않는다
  PawnUtility.ShouldCollideWithPawns / PawnBlockedBy: 전투 상태가 아니면 같은 편끼리 절대 막지 않는다.
       전투 상태이고 둘 다 '충돌 작업'(가장 가까운 적에게 접근, 공격 중 대기)이면 서로 막는다 → 폭 1 통로에서 한 줄
  AvoidGrid.PrintAvoidGridAroundTurret: 회피 격자는 포탑과 사선(닫힌 문은 막음)이 닿는 칸에만 → 닫힌 벽장 안 포탑은 회피 격자가 거의 없다
단순화: 바깥 건물·나무·기존 구조물은 무시, 지역 연결은 4방향 인접.
"""
import collections, json, pickle, sys

N = 275
arr_pkl, layout = sys.argv[1:3]
out = sys.argv[3] if len(sys.argv) > 3 else None
D = pickle.load(open(arr_pkl, "rb"))
th, TH = D["th"], D["TH"]
bp = json.load(open(layout))
ROCK = {"Limestone", "Sandstone", "Marble"}

def cells(r):
    for z in range(r[1], r[3] + 1):
        for x in range(r[0], r[2] + 1):
            yield x, z

def is_rock(x, z):
    t = TH.get(th[z, x])
    return bool(t) and (t in ROCK or t.startswith("Mineable"))

# 0 막힘, 1 보통, 2 문
K = [[0 if is_rock(x, z) else 1 for x in range(N)] for z in range(N)]
owner = {}
for s in bp["spaces"]:
    for c in cells(s["rect"]):
        K[c[1]][c[0]] = 1; owner[c] = s["id"]
for f in bp["fill"]:
    for c in cells(f["rect"]):
        K[c[1]][c[0]] = 0
for x, z in bp["coolers"] + [tuple(c) for c in bp.get("fl_walls", [])]:
    K[z][x] = 0
for x, z in bp["doors"] + bp.get("firedoors", []):
    K[z][x] = 2

def build_regions(K):
    reg = [[-1] * N for _ in range(N)]
    rid = 0; info = []
    for z in range(N):
        for x in range(N):
            if K[z][x] == 0 or reg[z][x] >= 0: continue
            t = K[z][x]
            if t == 2:
                reg[z][x] = rid; info.append(("door", 1)); rid += 1; continue
            x0, z0 = x - x % 12, z - z % 12
            q = collections.deque([(x, z)]); reg[z][x] = rid; n = 0
            while q:
                cx, cz = q.popleft(); n += 1
                for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, nz = cx + dx, cz + dz
                    if x0 <= nx < min(x0 + 12, N) and z0 <= nz < min(z0 + 12, N) and K[nz][nx] == 1 and reg[nz][nx] < 0:
                        reg[nz][nx] = rid; q.append((nx, nz))
            info.append(("normal", n)); rid += 1
    adj = collections.defaultdict(set)
    for z in range(N):
        for x in range(N):
            a = reg[z][x]
            if a < 0: continue
            for dx, dz in ((1, 0), (0, 1)):
                nx, nz = x + dx, z + dz
                if nx < N and nz < N and reg[nz][nx] >= 0 and reg[nz][nx] != a:
                    adj[a].add(reg[nz][nx]); adj[reg[nz][nx]].add(a)
    return reg, info, adj

def enemies_nearby(start, targets, reg, info, adj, max_regions):
    """EnemiesAreNearby 재현: 시작 지역부터 너비우선, 문 지역은 세지 않음. 목표 지역을 만나면 그때까지 센 지역 수를 반환."""
    r0 = reg[start[1]][start[0]]
    if r0 < 0: return None
    seen = {r0}; q = collections.deque([r0]); counted = 0
    while q:
        r = q.popleft()
        if r in targets: return counted
        if info[r][0] != "door": counted += 1
        if counted >= max_regions: return None
        for n in adj[r]:
            if n not in seen:
                seen.add(n); q.append(n)
    return None

def analyse(K, hostile_cells, label):
    reg, info, adj = build_regions(K)
    targets = {reg[z][x] for x, z in hostile_cells if reg[z][x] >= 0}
    mz = [c for c, o in owner.items() if o.startswith("MZ") or o == "LR"]
    mouth = tuple(next(s for s in bp["spaces"] if s["id"] == "MZT")["rect"][:2])
    outside = [(x, z) for z in range(mouth[1] - 30, mouth[1]) for x in range(mouth[0] - 30, mouth[0] + 30)
               if 0 <= x < N and 0 <= z < N and K[z][x] == 1 and (x, z) not in owner]
    on18 = [c for c in mz if enemies_nearby(c, targets, reg, info, adj, 18) is not None]
    out18 = [c for c in outside if enemies_nearby(c, targets, reg, info, adj, 18) is not None]
    near = min((abs(c[0] - mouth[0]) + abs(c[1] - mouth[1]) for c in out18), default=None)
    far = max((abs(c[0] - mouth[0]) + abs(c[1] - mouth[1]) for c in out18), default=None)
    off = sorted(set(mz) - set(on18))
    print(f"[{label}] 지역 {len(info)}개. 미로·사로 {len(mz)}칸 중 전투 상태 켜짐 {len(on18)}칸, 꺼짐 {len(off)}칸 {off[:6]}")
    print(f"    미로 입구 밖 30칸 반경 바깥 칸 {len(outside)}개 중 전투 상태 켜지는 칸 {len(out18)}개 (입구에서 맨해튼 {near}~{far})")
    return dict(maze_on=len(on18), maze_off=len(off), maze_off_cells=off, outside_on=len(out18), outside_total=len(outside))

# 기준: 사수 6 + 근접 3 + 대기실
colonists = [tuple(c) for c in bp["killzone"]["shooters"]] + [(152, 178)] + [tuple(c) for c in bp.get("melee_spots", [])]
res = {"사수·근접 위치만": analyse(K, colonists, "사수·근접 위치만")}

# 벽장 속 꺼진 포탑(설계): 적대 'AttackTarget'이므로 전투 상태 판정에 들어간다
bait = [tuple(c) for c in bp.get("bait_turret", [])]
if bait:
    res["벽장 꺼진 포탑 포함"] = analyse(K, colonists + bait, "벽장 꺼진 포탑 포함")

    def los(a, b):
        """GenSight.LineOfSight 정수 걷기(standoff_sim과 같음). 바위·벽·닫힌 문에서 막힘, 시작·끝 칸 제외."""
        (x0, z0), (x1, z1) = a, b
        flag = (x0 < x1) if x0 != x1 else (z0 < z1)
        nx, nz = abs(x1 - x0), abs(z1 - z0)
        x, z = x0, z0
        n = 1 + nx + nz
        sx = 1 if x1 > x0 else -1; sz = 1 if z1 > z0 else -1
        nx *= 4; nz *= 4
        err = nx // 2 - nz // 2
        while n > 1:
            if (x, z) != (x0, z0) and K[z][x] != 1:
                return False
            if err > 0 or (err == 0 and flag): x += sx; err -= nz
            else: z += sz; err += nx
            n -= 1
        return True
    door = next(d for d in map(tuple, bp["doors"]) if any(abs(d[0] - t[0]) + abs(d[1] - t[1]) == 1 for t in bait))
    side = {c for c, o in owner.items() if o in ("BTA", "BTB", "BTT")}
    enemy_cells = [(x, z) for z in range(N) for x in range(N) if K[z][x] == 1 and (x, z) not in side
                   and owner.get((x, z), "MZ").startswith(("MZ", "LR"))]
    # JobGiver_AITrashColonyClose: 적 칸 중심 11×11(반경 5) 안 + 사선이 있는 건물을 부순다
    trash = [c for c in enemy_cells for b in (door, *bait)
             if max(abs(c[0] - b[0]), abs(c[1] - b[1])) <= 5 and los(c, b)]
    # AvoidGrid: 포탑 사거리+4 안, 걸을 수 있고 포탑까지 사선이 닿는 칸
    avoid = [(x, z) for z in range(N) for x in range(N) if K[z][x] in (1, 2) for t in bait
             if (x - t[0]) ** 2 + (z - t[1]) ** 2 <= 32.9 ** 2 and (x, z) != t and los((x, z), t)]
    print(f"    벽장 문·포탑을 부수기 범위(반경 5)+사선으로 볼 수 있는 적 칸: {len(trash)}개 {trash[:5]}")
    print(f"    회피 격자가 생기는 칸(포탑과 사선, 사거리+4): {len(avoid)}개 {avoid[:5]}")
    res["bait_trash_exposed"] = trash; res["bait_avoid_cells"] = avoid
if out:
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
