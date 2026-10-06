# -*- coding: utf-8 -*-
"""아스테라스 기지 설계 v3(킬존 반영): 배치 정의 + 기계 검증.

사용: python3 -I tools/design.py <arr.pkl> <things.pkl> <out_dir>
좌표: 게임 좌표 (x 서→동, z 남→북). 사각형 (x0, z0, x1, z1) 양끝 포함.

검증 항목
  V1 겹침 / 서로 다른 공간이 벽 없이 맞닿음
  V2 단일 출입구: 킬존(미로+사로)을 막으면 외부에서 내부로 가는 길이 0이어야 함
  V3 모든 내부 공간이 외부와 연결(정착민이 드나들 수 있음)
  V4 고아 굴착 칸: 이미 파여 있지만 어떤 공간에도 속하지 않고 되메우지도 않은 칸 = 0
  V5 야외 시설이 암반·물·지붕 위에 놓이지 않음
  V6 미로 진입 터널을 제외한 모든 내부 공간이 100% 두꺼운 산 지붕 아래
  V7 1단계 완료 시점에도 단일 출입구 유지 + 냉동고·주방·대기실 연결
  V8 층 순서: 방폭문 D1을 막으면 킬존 밖으로 못 나가고, 근접 방어 문을 막으면 대기실 밖으로 못 나감
  V9 두 방폭문이 모두 열려도 사로에서 대기실·응급실·주 통로로 직선 사선이 없음
  V10 사대 모든 칸에서 입구가 보임(+사로 가시율 보고)
  V11 미로는 지름길 없는 외길
  보고: 동선 거리, 방별 암반 두께(바깥까지), 두꺼운 지붕 비율, 감염 가능 칸, 채굴량, 광맥
"""
import collections, json, pickle, re, sys

N = 275
P1, P2, P3, P4 = 1, 2, 3, 4

# ------------------------------------------------------------------ 배치 ----
# (id, 이름, 종류, rect, 단계, 용도/근거)
# 킬존 층(바깥 → 안):
#   미끼 포탑(전원 OFF) → 미로(MZ*, 장애물) → 입구(171,179) → 사로·개활지(LR 동쪽) → 사대(LR 서쪽 x151~153)
#   → 방폭문 D1(151,183) → U자 전실 V → 방폭문 D2(152,185) → 전투 대기실 WR → 근접 방어 문(156,187)
#   → 근접 방어선(주 통로 155~157,188) → 응급실 ER
SPACES = [
    # ── 킬존 ──
    ("MZT", "미로: 진입 터널", "corridor", (186, 168, 186, 172), P1,
     "산 표면(186,167)에서 시작. 문 없음 — 열린 길이 있어야 일반 습격이 벽을 파지 않는다."),
    ("MZA", "미로: 1구간", "corridor", (178, 173, 186, 173), P1, "서쪽 9칸. 바리케이드 격칸(이동 속도 24%, 그 위에선 멈춰 쏘기·엄폐 불가)."),
    ("MZ1", "미로: 굽이 1", "corridor", (178, 174, 178, 174), P1, "180° 꺾임."),
    ("MZB", "미로: 2구간", "corridor", (178, 175, 186, 175), P1, "동쪽 9칸. 바리케이드 격칸."),
    ("MZ2", "미로: 굽이 2", "corridor", (186, 176, 186, 178), P1, "북쪽 3칸."),
    ("MZC", "미로: 3구간 → 입구", "corridor", (171, 179, 186, 179), P1,
     "서쪽 16칸, 끝 (171,179)이 사로 입구. 장애물 없음 → 한 줄로 사로에 진입."),
    ("LR", "사로·개활지 + 사대", "room", (151, 176, 170, 182), P1,
     "20×7. 입구(171,179)에서 사대 앞 모래주머니(x=154)까지 엄폐물 없는 16칸. 사대는 서쪽 3열(x151~153). 냉동고 냉각기가 사대 뒤 벽에서 배기."),
    ("V", "방폭 전실(U자)", "corridor", (151, 184, 151, 185), P1,
     "D1(151,183) → 북쪽 2칸 → D2(152,185)로 동쪽 꺾임. 사로에서 대기실로 가는 직선이 존재할 수 없는 U자 구조(V9로 확인)."),
    ("WR", "전투 대기실·무기고", "room", (153, 184, 160, 186), P1,
     "8×3. 무기·방어구 선반, 안락의자·조각·식물, 소화 팝퍼. 사대까지 문 2개·전실 2칸."),
    ("ER", "응급실(병원)", "room", (151, 190, 159, 197), P2,
     "9×8. 근접 방어선 바로 뒤. 병원 침대 6 + 생체 모니터 + 의약품 선반. 무균 타일. 기지 유일의 병원."),
    # ── 주 통로·연결 ──
    ("M1W", "주 통로 서", "corridor", (126, 188, 136, 188), P2, "창고 북문·작업장 연결."),
    ("M1C", "주 통로 중앙(근접 방어선)", "corridor", (137, 188, 158, 188), P1,
     "근접 방어 문(156,187) 앞. 근접 전투원이 (155·156·157, 188)에 서면 문간의 적을 정면+양 대각선에서 동시에 친다."),
    ("M1E", "주 통로 동", "corridor", (159, 188, 186, 188), P2, "침실 구역 남열 연결."),
    ("TA", "창고-냉동고 통로", "corridor", (137, 181, 137, 187), P1, "기존 터널 북쪽 절반. 창고 문(136,181)과 냉동고 문(138,181)이 마주 봄. 남쪽 절반은 되메움."),
    ("TB", "서비스 통로", "corridor", (137, 189, 137, 218), P2, "기존 터널 + 북쪽 연장. 주 통로 ↔ 서쪽 생산 구역 ↔ 주방 ↔ 수경 ↔ 격리동."),
    ("C2", "배터리실 복도", "corridor", (130, 197, 135, 197), P2, "서비스 통로 ↔ 배터리실."),
    ("C3", "동쪽 복도", "corridor", (161, 189, 161, 218), P2, "주 통로 ↔ 침실 복도 ↔ 연구실 ↔ 부부 침실 ↔ 감옥."),
    ("CV", "침실-대회당 연결 복도", "corridor", (188, 196, 188, 209), P2, "침실 복도 동쪽 끝 ↔ 대회당 동문."),
    ("CB", "침실 복도", "corridor", (162, 196, 187, 196), P2, "독실 10실이 양쪽으로 붙는다. 킬존 출구(근접 방어선)에서 약 15칸."),
    # ── 식량: 수경 → 주방 → 냉동고 → 대회당 ──
    ("FRZ", "냉동고", "room", (139, 176, 149, 186), P1,
     "기존 방 R2. -20°C(감염 불가). 냉각기 3기가 사대 뒤 벽(x=150)에서 배기 — 사로는 미로로 바깥과 이어져 외기 온도. 도축대."),
    ("KIT", "주방", "room", (139, 190, 149, 194), P1, "전기 조리대 2. 냉동고까지 문 2개·3칸, 수경재배실과 문 하나."),
    ("HYD1", "수경재배실 1", "room", (139, 196, 149, 206), P2, "태양등 (144,201) + 수경재배기 약 12기 ≈ 7인분."),
    ("HYD2", "수경재배실 2", "room", (139, 208, 149, 218), P3, "인구 8명 초과 시. 태양등 (144,213). 합계 ≈ 15인분."),
    ("STO", "중앙 창고", "room", (125, 176, 135, 186), P1, "기존 방 R1(굴착 0). 선반. 궤도 무역 신호기. 작업장과 주 통로를 사이에 두고 마주 봄."),
    # ── 침실(돌파·공병의 목표) — 킬존 출구 바로 뒤, 산 깊은 곳 ──
    ("BC", "부부 침실", "room", (163, 204, 168, 208), P2, "6×5. 계율상 배우자만 동침."),
    ("CH", "대회당 복도", "corridor", (162, 210, 168, 210), P2, "동쪽 복도 ↔ 대회당."),
    ("HALL", "대회당", "room", (170, 204, 186, 214), P2,
     "17×11. 침실 구역 바로 북쪽, 산 깊은 곳. 식사·오락·이념 의식·지도자 연설. 식사 선반(주방에서 보충). 작위를 받으면 왕좌."),
    ("PRIS", "감옥", "room", (151, 207, 159, 212), P2, "9×6, 수감 침대 3. 죄수 침대도 돌파·공병의 목표라 침실 구역에 둔다."),
    ("LAB", "연구실", "room", (151, 199, 159, 205), P2, "하이테크 연구대·다중분석기·통신 콘솔."),
    # ── 서쪽 생산 구역(돌파 목표가 아닌 시설) ──
    ("WS", "작업장", "room", (125, 190, 135, 195), P2,
     "기계가공·제작대·전기 재봉·대장간·석재 절단 2·의약품 제조·바이오연료 정제·화장장."),
    ("BAT", "배터리·비상발전실", "room", (131, 199, 135, 205), P2, "배터리 10 + 화학연료 발전기 2. 사람이 머물지 않는 방."),
    ("MECH", "메카 정비소", "room", (151, 214, 159, 220), P3, "후반: 메카링크 확보 후."),
    ("CONT", "격리동", "room", (128, 215, 135, 221), P3, "모노리스 조사 시작 시 건설. 구속대 3 + 전기 억제기. 침실과 최대한 멀리."),
]
BED_X = [163, 168, 173, 178, 183]
BED_ROWS = [(190, 194, 195), (198, 202, 197)]
for r, (z0, z1, dz) in enumerate(BED_ROWS):
    for c, x0 in enumerate(BED_X):
        SPACES.append((f"B{r+1}{c+1}", f"침실 {r*5+c+1}", "room", (x0, z0, x0 + 3, z1), P2,
                       "4×5 독실. 킬존 출구 뒤 깊은 곳(돌파·공병의 목적지가 침대이므로)."))

KILLZONE = ("MZT", "MZA", "MZ1", "MZB", "MZ2", "MZC", "LR")   # 바깥과 이어진 전투 구역
D1, D2, MELEE = (151, 183), (152, 185), (156, 187)
ENTRANCE = (171, 179)
FIRING_LINE = (151, 176, 153, 182)
DOORS = [
    D1, D2, MELEE,                          # 방폭문 2, 근접 방어 문
    (155, 189),                             # 응급실 ↔ 근접 방어선
    (136, 181), (138, 181),                 # 창고 / 냉동고 ↔ TA
    (127, 187), (144, 187),                 # 창고 / 냉동고 ↔ 주 통로
    (169, 210), (187, 209),                 # 대회당 ↔ 대회당 복도 / 연결 복도
    (144, 189), (144, 195), (138, 192),     # 주방
    (138, 201), (144, 207),                 # 수경 1·2
    (160, 202), (160, 210),                 # 연구실·감옥 ↔ C3
    (162, 206),                             # 부부 침실 ↔ C3
    (130, 189),                             # 작업장 ↔ 주 통로
    (133, 198), (136, 197),                 # 배터리실 ↔ C2 ↔ TB
    (160, 217), (136, 218),                 # 메카 정비소 ↔ C3 / 격리동 ↔ TB
]
for r, (z0, z1, dz) in enumerate(BED_ROWS):
    for x0 in BED_X:
        DOORS.append((x0 + 1, dz))
FIREDOORS = [(136, 188), (160, 188)]   # 주 통로 구획 방화문

FILL = [  # (rect, 설명, 단계)
    ((137, 166, 137, 168), "옛 입구 봉인(벽 3칸). 외부 숨김 전선 인입구. 해체하면 비상 탈출구.", P1),
    ((144, 175, 144, 175), "R2 옛 남문(냉동고 단열)", P1),
    ((137, 169, 137, 175), "옛 입구 터널 되메움", P2),
    ((137, 176, 137, 180), "옛 터널 TA 남쪽 절반 되메움(건설 벽 이음매를 내부에서 멀리)", P2),
    ((130, 174, 136, 174), "옛 통로 되메움", P2),
    ((138, 174, 144, 174), "옛 통로 되메움", P2),
    ((139, 170, 149, 172), "옛 침실 되메움", P2),
    ((138, 171, 138, 171), "옛 침실 문 자리", P2),
    ((130, 175, 130, 175), "R1 옛 남문", P2),
]
COOLERS = [(150, 177), (150, 179), (150, 181)]
SANDBAGS = (154, 176, 154, 182)
TURRETS = []   # 킬존 시야 안 포탑 금지: AvoidGrid는 전원과 무관하게 포탑을 회피 → 똑똑한 돌파·공병 우회(raid_sim)
BARRICADES = [(x, 173) for x in range(179, 187, 2)] + [(x, 175) for x in range(179, 187, 2)]
BAIT = [(183, 166), (188, 165)]               # 미끼 가구: 포탑이 아닌 값싼 가구(반경 5칸 '부수기' 대상, 회피 격자 없음)
SUNLAMPS = [(144, 201), (144, 213)]
MELEE_SPOTS = [(155, 188), (156, 188), (157, 188)]

OUTDOOR = [
    ("F1", "밭 1: 쌀", (110, 146, 129, 160), P1, "300칸. 생장기 대량 생산 → 냉동 비축."),
    ("F2", "밭 2: 옥수수·면화·힐루트", (110, 130, 129, 144), P2, "300칸."),
    ("OLD", "기존 지상 건물", (131, 150, 143, 162), P1, "침실 완공 전까지 숙소. 이후 철거 → 태양광 부지."),
    ("SOL", "태양광", (131, 138, 150, 149), P2, "12기."),
    ("WIND", "풍력", (110, 118, 130, 127), P3, "2기."),
    ("GRAVE", "묘지", (133, 127, 141, 133), P2, "장례 의식."),
    ("FISH", "낚시 연못", (97, 123, 108, 133), P2, "보조 식량."),
]
POINT_OUT = [((118, 165), "박격포 1"), ((124, 165), "박격포 2"), ((230, 133), "지열 발전기"),
             (BAIT[0], "미끼 가구 1"), (BAIT[1], "미끼 가구 2")]
CONDUIT = [(230, 133), (152, 133), (152, 163), (137, 163), (137, 165)]
TEMP_GEN = [((145, 153), "목재 발전기 1 (1단계 임시)"), ((145, 156), "목재 발전기 2 (1단계 임시)")]

ROUTES = [("B25", "HALL", "가까운 침실→대회당"), ("B11", "HALL", "가장 먼 침실→대회당"),
          ("KIT", "FRZ", "주방→냉동고"), ("HYD1", "KIT", "수경1→주방"),
          ("LR", "ER", "사대→응급실(부상자 후송)"), ("WR", "LR", "대기실→사대(투입)"),
          ("B25", "WR", "가장 먼 침실→대기실(소집)"), ("WS", "STO", "작업장→창고"), ("KIT", "HALL", "주방→대회당(식사 보충)"),
          ("ER", "PRIS", "응급실→감옥"), ("B11", "CONT", "가장 가까운 침실→격리동(멀수록 좋음)")]

# ------------------------------------------------------------------ 유틸 ----
ROCK = {"Limestone", "Sandstone", "Marble"}

def cells(r):
    for z in range(r[1], r[3] + 1):
        for x in range(r[0], r[2] + 1):
            yield x, z

def P(s):
    a = re.findall(r"-?\d+", s)
    return int(a[0]), int(a[2])

def main():
    arr_pkl, things_pkl, out = sys.argv[1:4]
    D = pickle.load(open(arr_pkl, "rb"))
    top, roof, th, T, TH, R = [D[k] for k in "top roof th T TH R".split()]
    rows = pickle.load(open(things_pkl, "rb"))

    def is_rock(x, z):
        t = TH.get(th[z, x])
        return bool(t) and (t in ROCK or t.startswith("Mineable"))

    # 기본 격자: 0=통행 1=암반 2=건설벽 3=문 4=물
    G = [[0] * N for _ in range(N)]
    for z in range(N):
        for x in range(N):
            if is_rock(x, z):
                G[z][x] = 1
            elif T.get(top[z, x]) == "WaterShallow":
                G[z][x] = 0  # 얕은 물은 통행 가능
    for r in rows:   # 기존 플레이어 벽·문
        if r["fac"] == "Faction_152" and r["pos"] and r["def_"] in ("Wall",):
            x, z = P(r["pos"]); G[z][x] = 2
        if r["fac"] == "Faction_152" and r["pos"] and r["def_"] == "Door":
            x, z = P(r["pos"]); G[z][x] = 3
    pre_open = {(x, z) for z in range(N) for x in range(N)
                if G[z][x] == 0 and R.get(roof[z, x]) == "Thick"}   # 이미 파인 산 속 칸(자연 동굴 포함)

    problems = []
    owner, kind_of = {}, {}
    rep = collections.OrderedDict()
    ore = collections.Counter()
    for sid, name, kind, rect, ph, note in SPACES:
        kind_of[sid] = kind
        new = old = thick = 0
        for c in cells(rect):
            if c in owner:
                problems.append(f"V1 겹침 {sid}/{owner[c]} {c}")
                continue
            owner[c] = sid
            x, z = c
            if is_rock(x, z):
                new += 1
                t = TH.get(th[z, x])
                if t.startswith("Mineable"):
                    ore[t] += 1
            else:
                old += 1
            thick += R.get(roof[z, x]) == "Thick"
        n = (rect[2] - rect[0] + 1) * (rect[3] - rect[1] + 1)
        rep[sid] = dict(name=name, size=f"{rect[2]-rect[0]+1}x{rect[3]-rect[1]+1}", cells=n, mine=new,
                        existing=old, thick_pct=round(100 * thick / n))
    for sid, name, kind, rect, ph, note in SPACES:
        if sid != "MZT" and rep[sid]["thick_pct"] < 100:
            problems.append(f"V6 두꺼운 산 지붕이 아닌 칸 포함: {sid} ({rep[sid]['thick_pct']}%)")
    # 설계 적용
    for c, sid in owner.items():
        G[c[1]][c[0]] = 0
    for (x, z) in DOORS + FIREDOORS:
        if (x, z) in owner and (x, z) not in FIREDOORS:
            problems.append(f"V1 문이 공간 내부에 있음 {(x, z)}/{owner[(x, z)]}")
        G[z][x] = 3
    fill_cells = set()
    for r, _, _ in FILL:
        for c in cells(r):
            fill_cells.add(c); G[c[1]][c[0]] = 2
    for (x, z) in COOLERS:
        G[z][x] = 2  # 냉각기는 벽 칸
    for (x, z) in TURRETS + BARRICADES:
        if owner.get((x, z)) is None:
            problems.append(f"V1 포탑/바리케이드가 공간 밖 {(x, z)}")
    # V1 맞닿음
    allowed = {frozenset(p) for p in [("MZT", "MZA"), ("MZA", "MZ1"), ("MZ1", "MZB"), ("MZB", "MZ2"), ("MZ2", "MZC"),
                                      ("MZC", "LR"), ("TA", "M1C"), ("TB", "M1C"), ("M1W", "M1C"), ("M1C", "M1E"),
                                      ("C3", "M1E"), ("C3", "CB"), ("C3", "CH"), ("CB", "CV")]}
    for (x, z), a in owner.items():
        for dx, dz in ((1, 0), (0, 1)):
            b = owner.get((x + dx, z + dz))
            if b and b != a and frozenset((a, b)) not in allowed:
                problems.append(f"V1 벽 없이 맞닿음 {a}-{b} {(x, z)}")
    # 문이 실제로 두 공간(또는 공간-바깥)을 잇는지
    for (x, z) in DOORS:
        nb = [owner.get((x + dx, z + dz)) for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        nb = [b for b in nb if b]
        if len(set(nb)) < 2:
            problems.append(f"V1 문이 두 공간을 잇지 않음 {(x, z)} 이웃={nb}")

    def passable(x, z):
        return G[z][x] in (0, 3)

    def bfs(sources, block=frozenset()):
        dist = {}
        q = collections.deque()
        for s in sources:
            if s not in block and passable(*s):
                dist[s] = 0; q.append(s)
        while q:
            x, z = q.popleft()
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, nz = x + dx, z + dz
                if 0 <= nx < N and 0 <= nz < N and (nx, nz) not in dist and (nx, nz) not in block and passable(nx, nz):
                    dist[(nx, nz)] = dist[(x, z)] + 1; q.append((nx, nz))
        return dist

    edge = [(x, z) for x in range(N) for z in (0, N - 1)] + [(x, z) for z in range(N) for x in (0, N - 1)]
    inner = {c for c, s in owner.items() if s not in KILLZONE}
    # V3
    reach = bfs(edge)
    unreached = sorted({owner[c] for c in inner if c not in reach})
    if unreached:
        problems.append(f"V3 바깥과 연결 안 됨: {unreached}")
    # V2
    kb = frozenset(c for c, s in owner.items() if s in KILLZONE)
    reach2 = bfs(edge, block=kb)
    leak = sorted({owner[c] for c in inner if c in reach2})
    if leak:
        problems.append(f"V2 킬박스를 우회하는 경로 존재: {leak}")
    # V7 1단계 완료 시점(공사 중간 상태)에도 단일 출입구·핵심 공간 연결 유지
    base = [[1 if is_rock(x, z) else 0 for x in range(N)] for z in range(N)]
    p1 = {c for sid, _, _, rect, ph, _ in SPACES if ph == P1 for c in cells(rect)}
    for (x, z) in p1:
        base[z][x] = 0
    for (x, z) in DOORS + FIREDOORS:
        nb = {owner.get((x + dx, z + dz)) for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))}
        if any(o and next(s_[4] for s_ in SPACES if s_[0] == o) == P1 for o in nb):
            base[z][x] = 0
    for r, _, ph in FILL:
        if ph == P1:
            for (x, z) in cells(r):
                base[z][x] = 1
    for (x, z) in COOLERS:
        base[z][x] = 1
    for r_ in rows:
        if r_["fac"] == "Faction_152" and r_["pos"] and r_["def_"] == "Wall":
            x, z = P(r_["pos"]); base[z][x] = 1

    def bfs1(src, block):
        seen = set(c for c in src if base[c[1]][c[0]] == 0 and c not in block)
        q = collections.deque(seen)
        while q:
            x, z = q.popleft()
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n_ = (x + dx, z + dz)
                if 0 <= n_[0] < N and 0 <= n_[1] < N and n_ not in seen and n_ not in block and base[n_[1]][n_[0]] == 0:
                    seen.add(n_); q.append(n_)
        return seen
    r1 = bfs1(edge, frozenset())
    r1b = bfs1(edge, kb)
    for sid in ("FRZ", "KIT", "TA", "WR", "M1C"):
        cs = [c for c, o in owner.items() if o == sid]
        if not any(c in r1 for c in cs):
            problems.append(f"V7 1단계: {sid} 바깥과 연결 안 됨")
        if any(c in r1b for c in cs):
            problems.append(f"V7 1단계: {sid} 킬박스 우회 경로 존재")
    # ── 킬존 검사 ──
    kz = {}
    sp_of = lambda c: owner.get(c)
    # V8 층 순서: D1을 막으면 바깥에서 닿는 공간은 킬존뿐, 근접 문을 막으면 킬존+전실+대기실뿐
    for label, blk, allowed_ids in (("D1", {D1}, set(KILLZONE)), ("근접문", {MELEE}, set(KILLZONE) | {"V", "WR"})):
        rr = bfs(edge, block=frozenset(blk))
        got = sorted({sp_of(c) for c in rr if sp_of(c)} - allowed_ids)
        if got:
            problems.append(f"V8 {label}을(를) 막아도 닿는 공간: {got}")
    kz["v8"] = "통과"
    # V9 사선·폭발 차단: 문을 모두 열린 것으로 보고, 사로(LR) 어느 칸에서도 대기실·응급실·주 통로에 직선이 닿지 않아야 함
    def los(a, b):
        (x0, z0), (x1, z1) = a, b
        n = max(abs(x1 - x0), abs(z1 - z0))
        for i in range(1, n):
            x = round(x0 + (x1 - x0) * i / n); z = round(z0 + (z1 - z0) * i / n)
            if G[z][x] in (1, 2):
                return False
        return True
    lr = [c for c, o in owner.items() if o == "LR"]
    protect = [c for c, o in owner.items() if o in ("WR", "ER", "M1C", "M1E")]
    leaks = [(a, b) for a in lr for b in protect if los(a, b)]
    if leaks:
        problems.append(f"V9 사로→보호구역 직선 사선 {len(leaks)}개, 예: {leaks[:3]}")
    kz["v9_lines_checked"] = len(lr) * len(protect)
    # V10 사대 전 칸에서 입구가 보이고, 사로 칸의 몇 %를 볼 수 있는지
    fl = list(cells(FIRING_LINE))
    blind = [c for c in fl if not los(c, ENTRANCE)]
    if blind:
        problems.append(f"V10 입구가 안 보이는 사대 칸: {blind}")
    lane = [c for c in lr if c[0] > SANDBAGS[0]]
    cover = [sum(los(f, c) for c in lane) / len(lane) for f in fl]
    kz["v10_min_lane_visibility_pct"] = round(100 * min(cover))
    kz["entrance_to_sandbag_cells"] = ENTRANCE[0] - SANDBAGS[0] - 1
    # V11 미로는 외길(지름길 없음): 미로 칸마다 미로 이웃 ≤ 2, 끝점 2개
    mz = {c for c, o in owner.items() if o.startswith("MZ")}
    deg = {c: sum((c[0] + dx, c[1] + dz) in mz for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))) for c in mz}
    if any(v > 2 for v in deg.values()) or sum(v == 1 for v in deg.values()) != 2:
        problems.append("V11 미로가 외길이 아님")
    kz["maze_cells"] = len(mz)
    kz["maze_barricades"] = len(BARRICADES)
    # 사대 폭발 대비: 사대 칸 수(사수 간격 확보용)
    kz["firing_line_cells"] = len(fl)
    # V4 고아 굴착 칸 (설계 영역 주변)
    orphans = sorted(c for c in pre_open if c not in owner and c not in fill_cells
                     and 105 <= c[0] <= 192 and 160 <= c[1] <= 225 and G[c[1]][c[0]] == 0)
    if orphans:
        problems.append(f"V4 고아 굴착 칸 {len(orphans)}: {orphans[:12]}")
    # V5 야외
    for oid, name, rect, ph, note in OUTDOOR:
        bad = [c for c in cells(rect) if is_rock(*c) or R.get(roof[c[1], c[0]]) == "Thick"]
        if oid not in ("FISH",) and len(bad) > 0:
            problems.append(f"V5 {oid} 암반/산지붕 위 {len(bad)}칸")
    for (x, z), name in POINT_OUT + TEMP_GEN:
        if is_rock(x, z) or R.get(roof[z, x]):
            problems.append(f"V5 {name} {(x, z)} 설치 불가 칸(암반/지붕)")
    for (ax, az), (bx, bz) in zip(CONDUIT, CONDUIT[1:]):
        for x in range(min(ax, bx), max(ax, bx) + 1):
            for z in range(min(az, bz), max(az, bz) + 1):
                if is_rock(x, z):
                    problems.append(f"V5 전선 경로가 암반 통과 {(x, z)}")

    # 보고: 동선
    def center(sid):
        r = next(s[3] for s in SPACES if s[0] == sid)
        return ((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
    routes = []
    for a, b, label in ROUTES:
        d = bfs([center(a)])
        routes.append(dict(a=a, b=b, label=label, steps=d.get(center(b))))
    # 보고: 암반 두께(바깥 통행 칸에서 암반을 몇 칸 뚫어야 방에 닿나)
    outside = {c for c in reach2 if c not in owner and R.get(roof[c[1], c[0]]) != "Thick"}
    rd = {}
    q = collections.deque()
    for (x, z) in outside:
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, nz = x + dx, z + dz
            if 0 <= nx < N and 0 <= nz < N and G[nz][nx] in (1, 2) and (nx, nz) not in rd:
                rd[(nx, nz)] = 1; q.append((nx, nz))
    while q:
        x, z = q.popleft()
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, nz = x + dx, z + dz
            if 0 <= nx < N and 0 <= nz < N and G[nz][nx] in (1, 2) and (nx, nz) not in rd:
                rd[(nx, nz)] = rd[(x, z)] + 1; q.append((nx, nz))
    for sid, name, kind, rect, ph, note in SPACES:
        best = None
        for (x, z) in cells(rect):
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                v = rd.get((x + dx, z + dz))
                if v is not None and (best is None or v < best):
                    best = v
        rep[sid]["rock_cover"] = best
        # 감염 가능 칸: 두꺼운 지붕 + 통행 + 냉동고 제외
        rep[sid]["infest_cells"] = 0 if sid == "FRZ" else sum(
            1 for (x, z) in cells(rect) if R.get(roof[z, x]) == "Thick")
    # 우회 굴착 비용: 킬박스를 쓰지 않고 바깥에서 각 공간까지 부숴야 하는 칸 수(암반·벽·문 = 1)
    INF = 10 ** 9
    cost = {}
    dq = collections.deque()
    for c in outside:
        cost[c] = 0; dq.append(c)
    while dq:
        x, z = dq.popleft()
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, nz = x + dx, z + dz
            if not (0 <= nx < N and 0 <= nz < N):
                continue
            w = 1 if (G[nz][nx] in (1, 2, 3) or (nx, nz) in kb) else 0
            nc = cost[(x, z)] + w
            if nc < cost.get((nx, nz), INF):
                cost[(nx, nz)] = nc
                (dq.appendleft if w == 0 else dq.append)((nx, nz))
    for sid, name, kind, rect, ph, note in SPACES:
        rep[sid]["bypass_dig"] = min(cost.get(c, INF) for c in cells(rect))
    total_new = sum(v["mine"] for v in rep.values())
    by_phase = collections.Counter()
    for s in SPACES:
        by_phase[s[4]] += rep[s[0]]["mine"]

    print("== 검증 ==")
    print("문제:", "없음" if not problems else "")
    for p in problems:
        print("  -", p)
    print(f"신규 채굴 {total_new}칸 (단계별 {dict(sorted(by_phase.items()))}), 되메움 {len(fill_cells)}칸, 광맥 {dict(ore)}")
    print("== 동선(걸음) ==")
    for r in routes:
        print(f"  {r['label']}: {r['steps']}")
    print("== 방별 ==")
    for k, v in rep.items():
        print(" ", k, v)

    bp = dict(spaces=[dict(id=s[0], name=s[1], kind=s[2], rect=s[3], phase=s[4], note=s[5], **{k: v for k, v in rep[s[0]].items() if k != "name"}) for s in SPACES],
              doors=[list(d) for d in DOORS], firedoors=[list(d) for d in FIREDOORS],
              fill=[dict(rect=r, note=n, phase=p) for r, n, p in FILL], coolers=COOLERS, sandbags=SANDBAGS, turrets=TURRETS,
              sunlamps=SUNLAMPS,
              outdoor=[dict(id=o[0], name=o[1], rect=o[2], phase=o[3], note=o[4]) for o in OUTDOOR],
              points=[dict(xz=list(p), name=n) for p, n in POINT_OUT], tempgen=[dict(xz=list(p), name=n) for p, n in TEMP_GEN],
              conduit=CONDUIT, routes=routes, barricades=BARRICADES, bait=[list(b) for b in BAIT], melee_spots=MELEE_SPOTS,
              killzone=dict(d1=list(D1), d2=list(D2), melee=list(MELEE), entrance=list(ENTRANCE), firing_line=FIRING_LINE,
                            ids=list(KILLZONE), checks=kz),
              stats=dict(new_mined=total_new, mined_by_phase=dict(by_phase), filled=len(fill_cells), ore=dict(ore)),
              problems=problems)
    json.dump(bp, open(f"{out}/layout_v3.json", "w"), ensure_ascii=False, indent=1)
    sys.exit(1 if problems else 0)

if __name__ == "__main__":
    main()
