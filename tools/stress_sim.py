# -*- coding: utf-8 -*-
"""킬존 스트레스 테스트: 아군 돌격소총 사수 vs 여러 적 조합을 몬테카를로로 돌린다.

사용: python3 -I tools/stress_sim.py <arr.pkl> <layout_v3.json> [out.json] [반복수]

무엇을 재현하나 (디컴파일 1.6 코드 요약):
  명중   ShotReport: 사수정확도^거리 × 무기정확도(3/12/25/40 구간 보간) × 몸크기(0.5~2) × (1-표적 엄폐)
         거리·엄폐는 쏘는 쪽의 실제 칸 기준. 엄폐·사선·몸 내밀기는 standoff_sim과 같은 규칙.
  방어구 ArmorUtility: 유효 방어 = max(방어-관통,0); 난수 < 유효/2 → 0, < 유효 → 절반(예리→둔기)
  통증   HediffSet.CalculatePain: Σ(피해 × 0.0125) / HealthScale × 통증배율 ≥ 0.8 → 쓰러짐
  보호막 CompShield: 원거리·폭발 피해 × 0.033만큼 에너지 감소, 0 미만이면 깨지며 그 피해도 흡수. 근접은 통과
  조준   Stance_Warmup: 표적이 쓰러지거나 사선이 끊기면 조준 취소(맞아도 취소 안 됨)
  근접   Verb_LaunchProjectile: AI 원거리 무기는 붙어 있는 근접 위협이 있으면 쏘지 않는다
  충돌   PawnUtility.PawnBlockedBy: 같은 편끼리는 서로 통과(외길이 한 줄로 세우지 않음). 서 있는 칸은 1명
  투명   CompSightstealer: 우리 폰의 시야 반경 14×lerp(0.33,1,밝기) 안 + 사선이면 드러남, 맞으면 드러남
  도주   인간 습격대는 40~70%가 쓰러지면 도주. 메카·동물(광분)·엔티티·휘청이는 자는 끝까지
  폭발   Explosion: 폭심에서 사선이 닿는 칸만 피해(감쇠 여부는 무기 XML → 최악으로 감쇠 없음 가정)
  보호막 CompProjectileInterceptor: 원 밖에서 쏜 적대 투사체만 막음, 폭발물은 경계에서 터짐(저보호막 반경 4.9, 30초, 250HP)
  수류탄 착지 후 100틱 뒤 폭발(회피 교리: 반응 60틱 + 2칸 이동 26틱)
  충돌   collide=True면 사격 중(서 있는) 적이 뒤따르는 적을 막는다 — 실제로는 둘 다 '충돌 작업'일 때만(JobGiver_AIGotoNearestHostile 등)
수치 출처는 아래 표의 주석. [가정]은 확인하지 못한 값이라 결과를 좌우하면 그렇게 보고한다.
단순화: 빗나간 탄의 오발 피해·출혈·화재 확산·근접 회피 기술은 넣지 않았다. 사대 접촉 후 근접전은 단순 DPS 교환.
"""
import collections, heapq, json, math, pickle, random, sys

N = 275
arr_pkl, layout = sys.argv[1:3]
out = sys.argv[3] if len(sys.argv) > 3 else None
RUNS = int(sys.argv[4]) if len(sys.argv) > 4 else 400
D = pickle.load(open(arr_pkl, "rb"))
th, TH = D["th"], D["TH"]
bp = json.load(open(layout))
ROCK = {"Limestone", "Sandstone", "Marble"}
DT = 6                                   # 틱 단위 시간 간격(0.1초)

def cells(r):
    for z in range(r[1], r[3] + 1):
        for x in range(r[0], r[2] + 1):
            yield x, z

def is_rock(x, z):
    t = TH.get(th[z, x])
    return bool(t) and (t in ROCK or t.startswith("Mineable"))

# ---------------------------------------------------------------- 격자·사선 (standoff_sim과 같은 규칙) ----
G = [[1 if is_rock(x, z) else 0 for x in range(N)] for z in range(N)]
owner = {}
for s in bp["spaces"]:
    for c in cells(s["rect"]):
        G[c[1]][c[0]] = 0; owner[c] = s["id"]
for f in bp["fill"]:
    for c in cells(f["rect"]):
        G[c[1]][c[0]] = 1
for x, z in bp["coolers"] + bp["doors"] + [tuple(c) for c in bp.get("fl_walls", [])]:
    G[z][x] = 1
LOWC = ({tuple(c) for c in bp["sandbag_cells"]} if "sandbag_cells" in bp else set(cells(bp["sandbags"]))) | {tuple(b) for b in bp.get("barricades", [])}
for x, z in LOWC:
    G[z][x] = 2
ADJ = [(0, 1), (1, 0), (0, -1), (-1, 0), (1, -1), (1, 1), (-1, 1), (-1, -1)]

def see(x, z): return G[z][x] != 1
def ang(dx, dz): return 0.0 if dx == 0 and dz == 0 else math.degrees(math.atan2(dx, dz)) % 360

def los(a, b):
    (x0, z0), (x1, z1) = a, b
    flag = (x0 < x1) if x0 != x1 else (z0 < z1)
    nx, nz = abs(x1 - x0), abs(z1 - z0)
    x, z = x0, z0
    n = 1 + nx + nz
    sx = 1 if x1 > x0 else -1; sz = 1 if z1 > z0 else -1
    nx *= 4; nz *= 4
    err = nx // 2 - nz // 2
    while n > 1:
        if (x, z) != (x0, z0) and not see(x, z):
            return False
        if err > 0 or (err == 0 and flag): x += sx; err -= nz
        else: z += sz; err += nx
        n -= 1
    return True

def lean(loc, tgt):
    a = ang(tgt[0] - loc[0], tgt[1] - loc[1])
    f1, f2, f3, f4 = a > 270 or a < 90, 90 < a < 270, a > 180, a < 180
    b = [not see(loc[0] + dx, loc[1] + dz) for dx, dz in ADJ]
    r = []
    if not b[1] and ((b[0] and not b[5] and f1) or (b[2] and not b[4] and f2)): r.append((loc[0] + 1, loc[1]))
    if not b[3] and ((b[0] and not b[6] and f1) or (b[2] and not b[7] and f2)): r.append((loc[0] - 1, loc[1]))
    if not b[2] and ((b[3] and not b[7] and f3) or (b[1] and not b[4] and f4)): r.append((loc[0], loc[1] - 1))
    if not b[0] and ((b[3] and not b[6] and f3) or (b[1] and not b[5] and f4)): r.append((loc[0], loc[1] + 1))
    if see(*loc): r.append(loc)
    return r

def can_hit(s, t): return any(los(a, b) for a in lean(s, t) for b in lean(t, s))

def cover(t, s):
    tot = 0.0
    for dx, dz in ADJ:
        c = (t[0] + dx, t[1] + dz)
        if c == s or G[c[1]][c[0]] == 0: continue
        base = 0.75 if G[c[1]][c[0]] == 1 else 0.55
        d = abs((ang(dx, dz) - ang(s[0] - t[0], s[1] - t[1]) + 180) % 360 - 180)
        if dx and dz: d *= 1.75
        f = 1 if d < 15 else 0.8 if d < 27 else 0.6 if d < 40 else 0.4 if d < 52 else 0.2 if d < 65 else 0
        if not f: continue
        dd = math.hypot(s[0] - c[0], s[1] - c[1])
        if dd < 1.9: f *= 0.3333
        elif dd < 2.9: f *= 0.66666
        tot += (1 - tot) * base * f
    return tot

# ---------------------------------------------------------------- 수치표 ----
def acc_curve(t, s, m, l):
    def f(d):
        if d <= 3: return t
        if d <= 12: return t + (s - t) * (d - 3) / 9
        if d <= 25: return s + (m - s) * (d - 12) / 13
        if d <= 40: return m + (l - m) * (d - 25) / 15
        return l
    return f
# 무기: 사거리, 조준틱, 연사수, 연사간격틱, 쿨다운틱, 피해, 관통, 정확도(근/단/중/장)
WEAPONS = {
    "AR":      dict(rng=30.9, warm=60, burst=3, gap=10, cool=102, dmg=11, ap=0.16, acc=acc_curve(.60, .70, .65, .55)),   # 위키 Assault rifle
    "minigun": dict(rng=30.9, warm=150, burst=25, gap=5, cool=90, dmg=10, ap=0.15, acc=acc_curve(.20, .25, .25, .18)),   # 위키 Minigun(검색 요약, 확인 필요)
    "sniper":  dict(rng=44.9, warm=210, burst=1, gap=0, cool=90, dmg=25, ap=0.38, acc=acc_curve(.50, .70, .88, .90)),    # 위키 Sniper rifle
    "hcb":     dict(rng=27.0, warm=75, burst=24, gap=5, cool=444, dmg=15, ap=0.22, acc=acc_curve(.22, .22, .22, .22)),   # 위키 Heavy charge blaster(평균 22%), 연사간격 [가정]
    "doomsday": dict(rng=36.0, warm=270, burst=1, gap=0, cool=270, dmg=50, ap=0.0, acc=None, blast=7.8, miss=0.0, fuse=0, oneuse=True),   # 위키 Doomsday: 반경 7.8, 폭탄 50. 빗나감 반경 [가정 0]
    "triple":  dict(rng=36.0, warm=270, burst=3, gap=20, cool=270, dmg=50, ap=0.10, acc=None, blast=3.9, miss=2.9, fuse=0, oneuse=True),  # 위키 Triple rocket launcher
    "frag":    dict(rng=12.9, warm=90, burst=1, gap=0, cool=160, dmg=50, ap=0.10, acc=None, blast=1.9, miss=1.9, fuse=100),              # 위키 Frag grenades(착지 후 100틱 뒤 폭발). 관통 [가정]
}
# 사격 정확도/칸 (위키 Shooting Accuracy 표): 사격 6 0.95, 9 0.965, 10≈0.968, 12 0.975, 14 0.98, 20 0.995(검색 요약)
SKILL_ACC = {6: 0.95, 8: 0.96, 10: 0.968, 12: 0.975, 14: 0.98, 20: 0.995}

# 적 유형: 속도(칸/초), 몸크기, 체력배율, 통증배율(None=통증 없음), 받는피해배율, 예리방어, 무기, 근접DPS, 근접관통, 진영
#   human 4.6 c/s, 통증 0.8 = 피해 64 [위키·코드]
ETYPES = {
    "raider_ar":   dict(spd=4.6, size=1.0, hs=1.0, pain=1.0, inc=1.0, arm=0.45, wpn="AR", skill=10, mdps=4.0, map=0.1, kind="human"),     # 아군과 같은 사양 [가정: 방탄조끼+방탄모 수준 0.45]
    "minigunner":  dict(spd=4.6, size=1.0, hs=1.0, pain=1.0, inc=1.0, arm=0.45, wpn="minigun", skill=8, mdps=4.0, map=0.1, kind="human"),
    "rocketeer":   dict(spd=4.6, size=1.0, hs=1.0, pain=1.0, inc=1.0, arm=0.30, wpn="doomsday", skill=8, mdps=4.0, map=0.1, kind="human"),
    "neanderthal": dict(spd=4.0, size=1.0, hs=1.0, pain=0.5, inc=0.75, arm=0.05, wpn=None, skill=6, mdps=9.0, mhit=12.0, map=0.15, kind="human"),  # 위키 유전자: 통증 ×0.5, 받는 피해 ×0.75. 속도·근접 [가정]
    "monosword":   dict(spd=4.6, size=1.0, hs=1.0, pain=1.0, inc=1.0, arm=0.45, wpn=None, skill=8, mdps=10.0, mhit=25.0, map=0.83, kind="human", shield=1.1),  # 위키 단분자검 평균 DPS 12·관통 83%, 보호막 1.1/0.033
    "fleshbeast":  dict(spd=4.0, size=1.0, hs=1.0, pain=1.0, inc=1.0, arm=0.0, wpn=None, skill=0, mdps=5.0, map=0.1, kind="entity"),   # '살종양' 정체 미확인 → 중형 근접 살덩이 짐승 [가정]
    "centipede":   dict(spd=1.9, size=1.8, hs=4.32, pain=None, inc=1.0, arm=0.72, wpn="hcb", skill=8, mdps=6.0, map=0.2, kind="mech"),  # 위키: 예리 72%, 1.9 c/s, 체력 432%. 몸크기 [가정]
    "triple_rkt":  dict(spd=4.6, size=1.0, hs=1.0, pain=1.0, inc=1.0, arm=0.30, wpn="triple", skill=8, mdps=4.0, map=0.1, kind="human"),
    "grenadier":   dict(spd=4.6, size=1.0, hs=1.0, pain=1.0, inc=1.0, arm=0.30, wpn="frag", skill=8, mdps=4.0, map=0.1, kind="human"),
    "sniper20":    dict(spd=4.6, size=1.0, hs=1.0, pain=1.0, inc=1.0, arm=0.30, wpn="sniper", skill=20, mdps=4.0, map=0.1, kind="human"),
    "impid":       dict(spd=5.5, size=1.0, hs=1.0, pain=1.0, inc=1.0, arm=0.05, wpn=None, skill=6, mdps=3.0, map=0.1, kind="human", spew=7.9),  # 위키: 화염 토사 7.9칸(1회). 속도 [가정]
    "megasloth":   dict(spd=4.8, size=4.0, hs=3.6, pain=1.0, inc=1.0, arm=0.0, wpn=None, skill=0, mdps=6.1, mhit=21.0, map=0.2, kind="animal"),  # 위키: 4.8 c/s, 체력 360%, 몸크기 4, DPS 6.1
    "sightstealer": dict(spd=4.83, size=0.8, hs=0.75, pain=1.0, inc=1.0, arm=0.0, wpn=None, skill=0, mdps=2.17, mhit=7.0, map=0.1, kind="entity", invis=True),  # 위키
    "shambler":    dict(spd=3.2, size=1.0, hs=1.0, pain=None, inc=1.0, arm=0.0, wpn=None, skill=0, mdps=3.0, map=0.1, kind="shambler"),  # 위키: 속도 ×0.7, 통증 없음
}
FLEE = {"human"}                   # 도주하는 진영

# ---------------------------------------------------------------- 지형 준비 ----
SHOOT5 = [tuple(c) for c in bp["killzone"]["shooters"]]
SIXTH = (152, 178)                 # 6번째 사수: 2열(엄폐 0). 아군 탄은 5칸 안 아군에 막히지 않음(VerbUtility.InterceptChanceFactorFromDistance)
POCKETS = [(153, 181), (153, 182)] # 미로·사로 동쪽 어디서도 안 보이는 칸(회피 칸)
start = tuple(next(s for s in bp["spaces"] if s["id"] == "MZT")["rect"][:2])
walk = {c for c in owner if G[c[1]][c[0]] != 1}
COST = {c: (42 if c in LOWC else 0) for c in walk}   # 바리케이드·모래주머니 경로비용(틱)

def path_to(goals):
    """start → goals 중 하나까지 최소 시간 경로(칸 목록). 칸당 기본 1, 대각 1.41, +경로비용/13."""
    dist = {start: 0.0}; prev = {}
    pq = [(0.0, start)]
    while pq:
        d, c = heapq.heappop(pq)
        if c in goals:
            p = [c]
            while p[-1] in prev: p.append(prev[p[-1]])
            return p[::-1]
        if d > dist[c]: continue
        for dx, dz in ADJ:
            n = (c[0] + dx, c[1] + dz)
            if n not in walk: continue
            if dx and dz and ((c[0] + dx, c[1]) not in walk or (c[0], c[1] + dz) not in walk): continue
            nd = d + (1.41 if dx and dz else 1.0) + COST[n] / 13
            if nd < dist.get(n, 1e9):
                dist[n] = nd; prev[n] = c; heapq.heappush(pq, (nd, n))
    return None

FL_ADJ = {(154, z) for z in range(176, 180)} | {(152, z) for z in range(176, 181)}
PATH = path_to(FL_ADJ)
lane_and_maze = [c for c in PATH]
ALL_SH = SHOOT5 + [SIXTH]
VIS = {}          # (적칸, 아군칸) → (적이 쏠 수 있나, 아군이 쏠 수 있나, 거리, 적 엄폐, 아군 엄폐)
for e in PATH:
    for s in ALL_SH + POCKETS:
        VIS[(e, s)] = (can_hit(e, s), can_hit(s, e), math.dist(e, s), cover(e, s), cover(s, e))

SHIELD_C, SHIELD_R = (158.5, 179.5), 4.9   # 저보호막 중심: 사대 동쪽 5칸(폭심이 사대에서 7.8칸 밖이 되도록)

def shield_cut(src, dst):
    """적 투사체 src→dst가 보호막 원과 만나는 첫 점(칸). 발사 지점이 원 안이면 막지 않음(CompProjectileInterceptor)."""
    sx, sz = src[0] + 0.5, src[1] + 0.5; tx, tz = dst[0] + 0.5, dst[1] + 0.5
    cx, cz = SHIELD_C
    if (sx - cx) ** 2 + (sz - cz) ** 2 <= SHIELD_R ** 2: return None
    dx, dz = tx - sx, tz - sz
    a = dx * dx + dz * dz; b = 2 * (dx * (sx - cx) + dz * (sz - cz)); c = (sx - cx) ** 2 + (sz - cz) ** 2 - SHIELD_R ** 2
    disc = b * b - 4 * a * c
    if a == 0 or disc < 0: return None
    t = (-b - math.sqrt(disc)) / (2 * a)
    if not 0 <= t <= 1: return None
    return (int(sx + dx * t), int(sz + dz * t))

def land_cell(tgt, miss):
    if miss <= 0: return tgt
    cand = [(tgt[0] + dx, tgt[1] + dz) for dx in range(-3, 4) for dz in range(-3, 4)
            if dx * dx + dz * dz <= miss * miss and see(tgt[0] + dx, tgt[1] + dz)]
    return random.choice(cand)

def hitchance(acc_per_cell, w, d, size, cov):
    a = acc_per_cell ** d * (w["acc"](d) if w["acc"] else 1.0) * max(0.5, min(2.0, size)) * (1 - cov)
    return max(0.0, min(1.0, a))

def armor_roll(dmg, ap, arm):
    eff = max(arm - ap, 0.0)
    r = random.random()
    if r < eff / 2: return 0.0
    if r < eff: return dmg / 2
    return dmg

# 급소 모형(인간형 기준, HealthScale배): 몸통 40(40%), 머리 25(10%), 목 25(7.5%), 다리 30×2(28%), 그 외 비치명(14.5%)
PARTS = [("torso", 40, 0.40), ("head", 25, 0.10), ("neck", 25, 0.075), ("legL", 30, 0.14), ("legR", 30, 0.14), ("arm", 9999, 0.145)]
LETHAL = {"torso", "head", "neck"}

class Unit:
    def __init__(self, kind, side, t0=0, cell=None, **kw):
        self.kind, self.side = kind, side
        self.p = dict(ETYPES[kind]) if side == "enemy" else dict(kw)
        self.dmg = collections.Counter(); self.painsum = 0.0
        self.down = self.dead = self.fled = False
        self.t0 = t0; self.cell = cell; self.idx = -1; self.nextmove = t0
        self.stance = None; self.stance_t = 0; self.target = None; self.shots = 0
        self.shield = self.p.get("shield", 0.0)
        self.revealed = not self.p.get("invis", False)
        self.used = False; self.standing = False; self.contact = False
        self.wpn = WEAPONS.get(self.p.get("wpn")) if self.p.get("wpn") else None

    @property
    def active(self): return not (self.down or self.dead or self.fled)

    def take(self, dmg, ap, ranged=True, explosive=False):
        if not self.active: return
        if self.shield > 0 and (ranged or explosive):
            self.shield -= dmg * 0.033
            if self.shield < 0: self.shield = -1.0      # 깨짐(53초 뒤 재충전 → 전투 시간 안엔 없음으로 처리)
            return
        dmg = armor_roll(dmg, ap, self.p["arm"]) * self.p.get("inc", 1.0)
        if dmg <= 0: return
        hs = self.p["hs"]
        r = random.random(); acc = 0
        for name, hp, w in PARTS:
            acc += w
            if r <= acc: break
        self.dmg[name] += dmg
        if name in LETHAL and self.dmg[name] >= hp * hs:
            self.dead = True; return
        if self.dmg["legL"] >= 30 * hs and self.dmg["legR"] >= 30 * hs:
            self.down = True
        if self.p.get("pain") is not None:
            self.painsum += dmg
            if self.painsum * 0.0125 / hs * self.p["pain"] >= 0.8:
                self.down = True
        if self.p.get("invis"):
            self.revealed = True

def run(scn, rng_seed, doctrine):
    random.seed(rng_seed)
    us_cells = SHOOT5 + ([SIXTH] if scn.get("six", True) else [])
    us = [Unit("colonist", "us", cell=c, spd=4.6, size=1.0, hs=1.0, pain=1.0, inc=1.0, arm=scn.get("our_arm", 0.45), skill=scn.get("our_skill", 10)) for c in us_cells]
    for u in us: u.wpn = WEAPONS["AR"]; u.home = u.cell
    en = []
    for kind, n in scn["enemies"]:
        for _ in range(n):
            en.append(Unit(kind, "enemy", t0=int(random.uniform(0, scn.get("spread", 8)) * 60)))
    glow = scn.get("glow", 0.0)
    flee_at = random.uniform(0.4, 0.7)
    shield_until = -1; shield_hp = 0; packs = doctrine.get("packs", 2) if doctrine.get("shield") else 0
    booms = []                     # (터질 틱, 폭심, 무기)
    collide = scn.get("collide", False)
    T, TMAX = 0, 60 * 240
    log = collections.Counter()
    standing = {}
    while T < TMAX:
        # --- 적 이동 ---
        for e in en:
            if not e.active or T < e.t0: continue
            if e.idx < 0: e.idx = 0; e.nextmove = T
            if e.contact or e.standing: continue
            # 원거리: 지금 칸에서 아군을 쏠 수 있고 사거리 안이면 멈춤(서 있는 칸 1명)
            if e.wpn:
                c = PATH[e.idx]
                if c not in standing and any(VIS[(c, u.cell)][0] and VIS[(c, u.cell)][2] <= e.wpn["rng"] for u in us if u.active and (c, u.cell) in VIS):
                    e.standing = True; standing[c] = e; continue
            if T >= e.nextmove:
                if e.idx >= len(PATH) - 1:
                    e.contact = True; log["contact"] += 1; continue
                if collide and PATH[e.idx + 1] in standing:
                    e.nextmove = T + DT; log["blocked_ticks"] += DT; continue   # 앞 칸에 사격 중인 아군이 서 있으면 통과 못 함(둘 다 충돌 작업일 때)
                e.idx += 1
                c0, c1 = PATH[e.idx - 1], PATH[e.idx]
                step = 1.41 if (c0[0] != c1[0] and c0[1] != c1[1]) else 1.0
                e.nextmove = T + int(60 * step / e.p["spd"]) + COST[c1]
                # 화염 토사: 사거리 7.9 안에 사수가 보이면 1회
                if e.p.get("spew") and not e.used:
                    if any(VIS.get((c1, u.cell), (0, 0, 99))[0] and VIS[(c1, u.cell)][2] <= e.p["spew"] for u in us if u.active):
                        e.used = True; log["spew"] += 1
                        for u in us:
                            if u.active and math.dist(u.cell, c1) <= 7.9 and los(c1, u.cell) and random.random() < 0.5:
                                u.take(random.uniform(8, 20), 0.0, ranged=False, explosive=True); log["burned"] += 1
        # --- 투명 해제(시야도둑) ---
        r_detect = 14 * (0.33 + 0.67 * glow)
        for e in en:
            if e.active and not e.revealed and e.idx >= 0:
                c = PATH[e.idx]
                if any(u.active and math.dist(u.cell, c) <= r_detect and los(u.cell, c) for u in us) or e.contact:
                    e.revealed = True
        # --- 적 사격 / 근접 ---
        for e in en:
            if not e.active or e.idx < 0: continue
            c = PATH[e.idx]
            if e.contact:
                tgt = min((u for u in us if u.active), key=lambda u: math.dist(u.cell, c), default=None)
                hit = e.p.get("mhit", 8.0)
                if tgt and random.random() < e.p["mdps"] * DT / 60 / hit:   # 근접: 평균 DPS를 1회 타격 피해로 나눈 확률
                    tgt.take(hit, e.p["map"], ranged=False)
                continue
            if not e.standing: continue
            w = e.wpn
            if e.stance is None:
                cand = [u for u in us if u.active and T >= getattr(u, "out_until", 0) and VIS[(c, u.cell)][0] and VIS[(c, u.cell)][2] <= w["rng"]]
                if not cand:
                    e.standing = False; standing.pop(c, None); continue
                # 적 AI 점수: 60-거리-엄폐×10 (+폭발물은 반경 안 아군 수 ×10.8)
                def score(u):
                    d = VIS[(c, u.cell)][2]; sc = 60 - min(d, 40) - 10 * VIS[(c, u.cell)][4] * 10 / 10
                    if w.get("blast"): sc += 10.8 * sum(1 for v in us if v.active and v is not u and math.dist(v.cell, u.cell) <= w["blast"])
                    return sc
                e.target = max(cand, key=score); e.stance = "warm"; e.stance_t = T + w["warm"]; e.shots = 0
                if w.get("blast"): log["rocket_aim"] += 1
            tgt = e.target
            if not tgt.active or not VIS[(c, tgt.cell)][0]:
                e.stance = None; log["aim_cancel"] += 1 if w.get("blast") else 0; continue
            if e.stance == "warm" and T >= e.stance_t:
                e.stance = "fire"; e.stance_t = T
            if e.stance == "fire" and T >= e.stance_t:
                d = VIS[(c, tgt.cell)][2]
                if w.get("blast"):
                    center = land_cell(tgt.cell, w["miss"])
                    cut = shield_cut(c, center) if shield_until > T and shield_hp > 0 else None
                    if cut:
                        center = cut; shield_hp -= w["dmg"]; log["blast_shielded"] += 1
                    log["blast_fired"] += 1
                    if w is WEAPONS["doomsday"] and not cut: log["rocket_fired"] += 1
                    booms.append((T + w["fuse"], center, w))
                    if w["fuse"] and doctrine.get("gdodge"):
                        # 수류탄 착지 후 100틱: 반응 60틱 + 서쪽 2칸(26틱) → 반경 1.9 밖으로 피함
                        for u in us:
                            if u.active and math.dist(u.cell, center) <= w["blast"] + 0.5 and 60 + 26 <= w["fuse"]:
                                u.out_until = T + w["fuse"] + 30; log["gdodge"] += 1
                    e.shots += 1
                    if e.shots >= w["burst"]:
                        if w.get("oneuse"):
                            e.wpn = None; e.standing = False; standing.pop(c, None); e.stance = None
                        else:
                            e.stance = "cool"; e.stance_t = T + w["cool"]
                    else:
                        e.stance_t = T + w["gap"]
                    continue
                cut = shield_cut(c, tgt.cell) if shield_until > T and shield_hp > 0 else None
                if cut:
                    shield_hp -= w["dmg"]
                else:
                    p = hitchance(SKILL_ACC[e.p["skill"]], w, d, 1.0, VIS[(c, tgt.cell)][4])
                    if random.random() < p: tgt.take(w["dmg"], w["ap"])
                e.shots += 1
                if e.shots >= w["burst"]:
                    e.stance = None; e.stance_t = 0; e.nextmove = T + w["cool"]
                    e.stance = "cool"; e.stance_t = T + w["cool"]
                else:
                    e.stance_t = T + w["gap"]
            if e.stance == "cool" and T >= e.stance_t:
                e.stance = None
        # --- 폭발 ---
        for b in [b for b in booms if b[0] <= T]:
            booms.remove(b)
            _, center, w = b
            for u in us:
                if u.active and T >= getattr(u, "out_until", 0) and math.dist(u.cell, center) <= w["blast"] and (u.cell == center or los(center, u.cell)):
                    u.take(w["dmg"], w["ap"], ranged=False, explosive=True); log["blast_victims"] += 1
                    if w is WEAPONS["doomsday"]: log["rocket_victims"] += 1
            for e2 in en:
                if e2.active and e2.idx >= 0:
                    c2 = PATH[e2.idx]
                    if math.dist(c2, center) <= w["blast"] and (c2 == center or los(center, c2)):
                        e2.take(w["dmg"], w["ap"], ranged=False, explosive=True); log["blast_enemy_hits"] += 1
        # --- 교리: 폭발물 조준 대응 ---
        for e in en:
            if e.active and e.stance == "warm" and e.wpn and e.wpn.get("blast"):
                if packs > 0 and (shield_until <= T or shield_hp <= 0):
                    packs -= 1; log["shield_used"] += 1; shield_until = T + 1800; shield_hp = 250
                if not e.wpn.get("oneuse"):
                    continue
                tgt = e.target
                free = [p_ for p_ in POCKETS if all(v.cell != p_ for v in us)]
                if doctrine.get("dodge") and tgt.active and tgt.cell not in POCKETS and free:
                    # 플레이어 반응 1초(60틱) + 이동(칸당 13틱) 안에 조준(270틱)이 끝나지 않으면 회피 성공 → 사선 끊김 → 조준 취소
                    steps = abs(tgt.cell[1] - free[0][1]) + abs(tgt.cell[0] - free[0][0])
                    if T >= e.stance_t - e.wpn["warm"] + 60 and T + steps * 13 < e.stance_t:
                        tgt.cell = free[0]; tgt.dodge_until = T + steps * 13 + 300; log["dodge"] += 1
        for u in us:
            if u.active and getattr(u, "dodge_until", None) and T >= u.dodge_until and u.cell in POCKETS:
                u.cell = u.home; u.dodge_until = None
        # --- 아군 사격 ---
        prio = {"rocketeer": 0, "triple_rkt": 0, "grenadier": 1, "sniper20": 1, "minigunner": 1, "centipede": 2, "raider_ar": 3}
        for u in us:
            if not u.active or u.cell in POCKETS or T < getattr(u, "out_until", 0): continue
            if u.stance is None:
                cand = []
                for e in en:
                    if not e.active or e.idx < 0 or not e.revealed: continue
                    c = PATH[e.idx]
                    v = VIS.get((c, u.cell))
                    if v and v[1] and v[2] <= u.wpn["rng"]:
                        cand.append((prio.get(e.kind, 4) if doctrine.get("focus", True) else 4, -e.idx, e))
                if not cand: continue
                cand.sort(key=lambda t: (t[0], t[1]))
                u.target = cand[0][2]; u.stance = "warm"; u.stance_t = T + u.wpn["warm"]; u.shots = 0
            e = u.target
            if not e.active or not e.revealed:
                u.stance = None; continue
            c = PATH[e.idx]; v = VIS.get((c, u.cell))
            if not v or not v[1]:
                u.stance = None; continue
            if u.stance == "warm" and T >= u.stance_t: u.stance = "fire"; u.stance_t = T
            if u.stance == "fire" and T >= u.stance_t:
                p = hitchance(SKILL_ACC[u.p["skill"]], u.wpn, v[2], e.p["size"], v[3])
                if random.random() < p:
                    e.take(u.wpn["dmg"], u.wpn["ap"]); log["our_hits"] += 1
                u.shots += 1
                if u.shots >= u.wpn["burst"]: u.stance = "cool"; u.stance_t = T + u.wpn["cool"]
                else: u.stance_t = T + u.wpn["gap"]
            if u.stance == "cool" and T >= u.stance_t: u.stance = None
        # --- 도주 ---
        humans = [e for e in en if e.p["kind"] in FLEE]
        if humans and sum(1 for e in humans if e.down or e.dead) >= flee_at * len(humans):
            for e in humans:
                if e.active: e.fled = True; log["fled"] += 1
        for c, e in list(standing.items()):
            if not e.active: standing.pop(c, None)
        if all(not e.active for e in en) or all(not u.active for u in us):
            break
        T += DT
    return dict(time=T / 60, us_down=sum(u.down or u.dead for u in us), us_dead=sum(u.dead for u in us),
                en_left=sum(e.active for e in en), contact=log["contact"], log=dict(log))

SCN = {
    "T1 혼합(미니건·센티피드·둠스데이·네안데르탈3·단분자검·살종양2)": dict(enemies=[("minigunner", 1), ("centipede", 1), ("rocketeer", 1), ("neanderthal", 3), ("monosword", 1), ("fleshbeast", 2)]),
    "T1a 둠스데이 단독": dict(enemies=[("rocketeer", 1)]),
    "T1b 센티피드 단독": dict(enemies=[("centipede", 1)]),
    "T1c 네안데르탈 3": dict(enemies=[("neanderthal", 3)]),
    "T1d 단분자검+보호막": dict(enemies=[("monosword", 1)]),
    "T2 혼합(저격20·임피드3·동급10·거대늘보3)": dict(enemies=[("sniper20", 1), ("impid", 3), ("raider_ar", 10), ("megasloth", 3)]),
    "T2a 동급 돌격소총 10": dict(enemies=[("raider_ar", 10)]),
    "T2a' 동급 돌격소총 10 (적끼리 충돌 가정)": dict(enemies=[("raider_ar", 10)], collide=True),
    "T2b 거대늘보 3": dict(enemies=[("megasloth", 3)]),
    "T2c 저격 20": dict(enemies=[("sniper20", 1)]),
    "T4a 삼연발 미사일 1": dict(enemies=[("triple_rkt", 1)]),
    "T4b 수류탄병 3": dict(enemies=[("grenadier", 3)]),
    "T4c 수류탄병 3 + 동급 돌격소총 5": dict(enemies=[("grenadier", 3), ("raider_ar", 5)]),
    "T4d 삼연발 1 + 수류탄 2 + 동급 5": dict(enemies=[("triple_rkt", 1), ("grenadier", 2), ("raider_ar", 5)]),
    "T3 시야도둑20·휘청30 (사로 어두움)": dict(enemies=[("sightstealer", 20), ("shambler", 30)], spread=20, glow=0.0),
    "T3L 시야도둑20·휘청30 (사로 조명)": dict(enemies=[("sightstealer", 20), ("shambler", 30)], spread=20, glow=1.0),
    "T3a 시야도둑 20 (어두움)": dict(enemies=[("sightstealer", 20)], spread=15, glow=0.0),
    "T3b 시야도둑 20 (조명)": dict(enemies=[("sightstealer", 20)], spread=15, glow=1.0),
    "T3c 휘청이는 자 30": dict(enemies=[("shambler", 30)], spread=20),
}
DOCTRINES = {"집중": dict(focus=True), "집중+회피": dict(focus=True, dodge=True, gdodge=True), "집중+저보호막": dict(focus=True, shield=True)}
BLAST = {"rocketeer", "triple_rkt", "grenadier"}

def summarize(rs):
    n = len(rs)
    return dict(win=round(100 * sum(r["en_left"] == 0 for r in rs) / n), contact=round(100 * sum(r["contact"] > 0 for r in rs) / n),
                us_down=round(sum(r["us_down"] for r in rs) / n, 2), us_dead=round(sum(r["us_dead"] for r in rs) / n, 2),
                p_down3=round(100 * sum(r["us_down"] >= 3 for r in rs) / n), time=round(sum(r["time"] for r in rs) / n),
                rocket_fired=round(100 * sum(r["log"].get("rocket_fired", 0) > 0 for r in rs) / n),
                rocket_victims=round(sum(r["log"].get("rocket_victims", 0) for r in rs) / n, 2),
                blast_victims=round(sum(r["log"].get("blast_victims", 0) for r in rs) / n, 2),
                blast_enemy_hits=round(sum(r["log"].get("blast_enemy_hits", 0) for r in rs) / n, 2))

if __name__ == "__main__":
    print(f"적 경로 {len(PATH)}칸 (미로 입구 {start} → 사대), 아군 사수 {len(SHOOT5)}+1, 반복 {RUNS}회")
    res = {}
    for name, scn in SCN.items():
        docs = DOCTRINES if any(k in BLAST for k, _ in scn["enemies"]) else {"집중": DOCTRINES["집중"]}
        for dn, doc in docs.items():
            for skill in (8, 12):
                s = dict(scn, our_skill=skill)
                rs = [run(s, i, doc) for i in range(RUNS)]
                m = summarize(rs)
                res[f"{name} | {dn} | 사격{skill}"] = m
                print(f"{name} | {dn} | 사격{skill}: 전멸시킴 {m['win']}% · 사대 근접 접촉 {m['contact']}% · "
                      f"아군 쓰러짐 {m['us_down']}명(사망 {m['us_dead']}) · 3명↑ 쓰러짐 {m['p_down3']}% · {m['time']}초"
                      + (f" · 폭발 피격 아군 {m['blast_victims']}회 / 적 {m['blast_enemy_hits']}회" if any(k in BLAST for k, _ in scn["enemies"]) else ""))
    if out:
        json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
