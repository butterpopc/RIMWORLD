# -*- coding: utf-8 -*-
"""아스테라스 기지 설계 v2: 배치 정의 + 기계 검증 + 렌더링.

사용: python3 -I tools/design.py <arr.pkl> <things.pkl> <out_dir>
좌표: 게임 좌표 (x 서→동, z 남→북). 사각형 (x0, z0, x1, z1) 양끝 포함.

검증 항목
  V1 겹침 / 서로 다른 공간이 벽 없이 맞닿음
  V2 단일 출입구: 킬박스(KB+MOUTH)를 막으면 외부에서 내부로 가는 길이 0이어야 함
  V3 모든 내부 공간이 외부와 연결(정착민이 드나들 수 있음)
  V4 고아 굴착 칸: 이미 파여 있지만 어떤 공간에도 속하지 않고 되메우지도 않은 칸 = 0
  V5 야외 시설이 암반·물·지붕 위에 놓이지 않음
  V6 입구 터널을 제외한 모든 내부 공간이 100% 두꺼운 산 지붕 아래
  V7 1단계 완료 시점에도 단일 출입구 유지 + 냉동고·주방 연결
  보고: 동선 거리, 방별 암반 두께(바깥까지), 두꺼운 지붕 비율, 감염 가능 칸, 채굴량, 광맥
"""
import collections, json, pickle, re, sys

N = 275
P1, P2, P3, P4 = 1, 2, 3, 4

# ------------------------------------------------------------------ 배치 ----
# (id, 이름, 종류, rect, 단계, 용도/근거)
SPACES = [
    # 출입·방어
    ("MOUTH", "입구 터널", "corridor", (165, 170, 165, 175), P1,
     "폭 1, 길이 6. 문을 달지 않는다(열린 길이 있어야 일반 습격이 벽을 뚫지 않는다). 매일 출입로로 사용."),
    ("KB", "킬박스 겸 현관", "room", (151, 176, 165, 183), P1,
     "적은 남동 모서리(165,176)로 한 명씩 들어와 엄폐물 없는 10칸을 서쪽으로 건너야 한다. 방어선은 서쪽 끝. 평시엔 현관·냉동고 배기실."),
    ("AIR", "에어록", "corridor", (152, 185, 152, 185), P1,
     "문(152,184) - 전실(152,185) - 문(152,186) - 연결칸(152,187). 독가스·화염·돌입을 이중 차단."),
    ("AIRC", "에어록 연결칸", "corridor", (152, 187, 152, 187), P1, "에어록 → 주 통로."),
    # 주 통로
    ("M1W", "주 통로 서", "corridor", (126, 188, 136, 188), P2, "대회당 북문 연결."),
    ("M1C", "주 통로 중앙", "corridor", (137, 188, 152, 188), P1, "1단계: 에어록 ↔ 기존 터널(TA·TB)을 잇는 최소 구간."),
    ("M1E", "주 통로 동", "corridor", (153, 188, 185, 188), P2, "병원·작업장·창고·감옥·격리동 연결."),
    ("TA", "식당-냉동고 통로", "corridor", (137, 176, 137, 187), P1, "기존 터널. 식당 문(136,181)과 냉동고 문(138,181)이 마주 봄 → 식사 동선 3칸."),
    ("TB", "서비스 통로", "corridor", (137, 189, 137, 213), P2, "기존 터널. 주 통로 ↔ 침실 복도 ↔ 주방 ↔ 수경재배실을 잇는다."),
    ("C2", "침실 복도", "corridor", (112, 197, 135, 197), P2, "독실 10실이 양쪽으로 붙는다."),
    ("BC", "부부 침실", "room", (130, 205, 135, 209), P2, "6×5. 계율상 배우자만 동침 → 부부 1쌍용."),
    # 식량 사슬: 수경 → 주방 → 냉동고 → 식당
    ("FRZ", "냉동고", "room", (139, 176, 149, 186), P1,
     "기존 방 R2. -20°C(감염 불가 온도). 냉각기 3기가 동쪽 벽(x=150)에서 킬박스로 배기(킬박스는 바깥과 이어져 외기와 같은 온도). 도축대 포함."),
    ("HALL", "대회당", "room", (119, 176, 135, 186), P2,
     "기존 방 R1 + 서쪽 6열 확장. 식사·오락·이념 의식(이념 상징물)·지도자 연설. 작위를 받으면 왕좌."),
    ("KIT", "주방", "room", (139, 190, 149, 194), P1,
     "전기 조리대 2. 냉동고까지 문 2개·3칸, 수경재배실과 문 하나."),
    ("HYD1", "수경재배실 1", "room", (139, 196, 149, 206), P2,
     "11×11, 태양등 1기(중앙 144,201) + 수경재배기 약 12기. 날씨·계절·낙진 무관 상시 식량 ≈7인분."),
    ("HYD2", "수경재배실 2", "room", (139, 208, 149, 218), P3,
     "인구 8명 초과 시 개방. 같은 규격. 합계 ≈15인분."),
    # 생활
    ("HOSP", "병원", "room", (151, 190, 159, 197), P2,
     "에어록 바로 뒤(주 통로 건너편). 병원 침대 6 + 수술. 무균 타일."),
    ("C3", "동쪽 복도", "corridor", (161, 189, 161, 206), P2, "주 통로 ↔ 연구실·창고."),
    ("PRIS", "감옥", "room", (178, 180, 184, 186), P2, "7×7, 수감 침대 3. 모집·몸값용(계율상 노예 없음)."),
    # 생산
    ("WS", "작업장", "room", (167, 179, 176, 186), P2,
     "기계가공·제작대·전기 재봉·대장간·석재 절단 2·의약품 제조·바이오연료 정제·화장장."),
    ("STO", "중앙 창고", "room", (163, 190, 177, 200), P2, "선반. 작업장과 주 통로를 사이에 두고 마주 봄. 궤도 무역 신호기."),
    ("LAB", "연구실", "room", (151, 199, 159, 205), P2, "하이테크 연구대·다중분석기·통신 콘솔."),
    ("BAT", "배터리·비상발전실", "room", (175, 202, 179, 208), P2,
     "배터리 10 + 화학연료 발전기 2. 산 표면에서 30칸 이상 안쪽. 사람이 머무르지 않는 방(합선 폭발 격리)."),
    ("MECH", "메카 정비소", "room", (163, 202, 173, 208), P3, "메카링크 확보 시: 재충전기·배양기·폐기물 처리."),
    ("CONT", "격리동", "room", (179, 190, 187, 198), P3,
     "자연암 벽 9×9. 구속대 3 + 전기 억제기. 침실(x≤135)과 45칸 이상 이격."),
]
# 침실 12실: 5×5
BED_X = [112, 117, 122, 127, 132]           # 4칸 폭
BED_ROWS = [(191, 195, 196), (199, 203, 198)]  # (z0, z1, 문 z)
for r, (z0, z1, dz) in enumerate(BED_ROWS):
    for c, x0 in enumerate(BED_X):
        SPACES.append((f"B{r+1}{c+1}", f"침실 {r*5+c+1}", "room", (x0, z0, x0 + 3, z1), P2,
                       "4×5 독실. 벽·바닥은 다듬은 자연암(재료 0)."))

DOORS = [
    (152, 184), (152, 186),                 # 에어록
    (136, 181), (138, 181),                 # 식당/냉동고 ↔ TA
    (127, 187), (144, 187),                 # 식당/냉동고 ↔ M1
    (144, 189), (144, 195), (138, 192),     # 주방
    (138, 201), (144, 207), (138, 213),     # 수경 1·2
    (155, 189), (181, 187),                 # 병원·감옥
    (171, 187), (170, 189), (162, 195),     # 작업장·창고
    (160, 202), (177, 201), (168, 201),     # 연구실·배터리실·메카
    (183, 189),                             # 격리동
    (136, 197), (136, 207),                 # 침실 복도·부부 침실 ↔ 서비스 통로
]
for r, (z0, z1, dz) in enumerate(BED_ROWS):
    for x0 in BED_X:
        DOORS.append((x0 + 1, dz))
FIREDOORS = [(136, 188), (150, 188), (162, 188)]  # 주 통로 구획 방화문(통로 안에 둠)

# 건설 벽: 봉인·되메우기 (벽은 전력을 전달 → 외부 전선 인입로 겸용)
FILL = [  # (rect, 설명, 단계)
    ((137, 166, 137, 168), "옛 입구 봉인(벽 3칸). 외부 숨김 전선이 이 벽을 타고 들어옴. 해체하면 비상 탈출구.", P1),
    ((137, 169, 137, 175), "옛 입구 터널 되메움", P2),
    ((130, 174, 136, 174), "옛 통로 되메움", P2),
    ((138, 174, 144, 174), "옛 통로 되메움", P2),
    ((139, 170, 149, 172), "옛 침실 되메움(표면에서 3~5칸 = 공병이 처음 닿는 곳, 감염 후보 제거)", P2),
    ((138, 171, 138, 171), "옛 침실 문 자리", P2),
    ((130, 175, 130, 175), "R1 옛 남문", P2),
    ((144, 175, 144, 175), "R2 옛 남문(냉동고 단열)", P1),
    ((137, 214, 137, 214), "채광 터널 북단 되메움(부품 광맥 채굴 후)", P2),
]
COOLERS = [(150, 177), (150, 180), (150, 183)]   # 냉동고 → 킬박스
SANDBAGS = (154, 176, 154, 183)
TURRETS = [(152, 177), (152, 182)]
SUNLAMPS = [(144, 201), (144, 213)]

OUTDOOR = [
    ("F1", "밭 1: 쌀", (110, 146, 129, 160), P1, "300칸. 생장기 대량 생산 → 냉동 비축."),
    ("F2", "밭 2: 옥수수·면화·힐루트", (110, 130, 129, 144), P2, "300칸."),
    ("OLD", "기존 지상 건물", (131, 150, 143, 162), P1, "1~2단계 임시 숙소. 침실 완공 후 철거(대리석 블록 회수) → 태양광 부지."),
    ("SOL", "태양광", (131, 138, 150, 149), P2, "12기. 낮 부하(태양등)와 시간대 일치."),
    ("WIND", "풍력", (110, 118, 130, 127), P3, "2기. 야간 보완."),
    ("APRON", "함정 앞마당", (160, 161, 170, 167), P2, "입구 직선 경로에 가시 함정. 정착민용 우회 칸 남김."),
    ("GRAVE", "묘지", (133, 127, 141, 133), P2, "장례 의식."),
    ("FISH", "낚시 연못", (97, 123, 108, 133), P2, "보조 식량."),
    ("PAD", "(선택) 중력선 계류장", (172, 138, 194, 158), P4, "중력 엔진 확보 + 운용 결정 시에만."),
]
POINT_OUT = [((118, 165), "박격포 1"), ((124, 165), "박격포 2"), ((230, 133), "지열 발전기")]
CONDUIT = [(230, 133), (152, 133), (152, 163), (137, 163), (137, 165)]   # 숨김 전선
TEMP_GEN = [((145, 153), "목재 발전기 1 (1단계 임시)"), ((145, 156), "목재 발전기 2 (1단계 임시)")]

# 동선 검사 쌍
ROUTES = [("B25", "HALL", "가까운 침실→대회당"), ("B11", "HALL", "가장 먼 침실→대회당"),
          ("KIT", "FRZ", "주방→냉동고"), ("FRZ", "HALL", "냉동고→대회당"), ("HYD1", "KIT", "수경1→주방"),
          ("HYD2", "FRZ", "수경2→냉동고"), ("KB", "HOSP", "킬박스→병원"), ("WS", "STO", "작업장→창고"), ("LAB", "STO", "연구실→창고"),
          ("B11", "KB", "가장 먼 침실→방어선"), ("HOSP", "PRIS", "병원→감옥"), ("B25", "CONT", "가장 가까운 침실→격리동(멀수록 좋음)")]

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
        if sid != "MOUTH" and rep[sid]["thick_pct"] < 100:
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
    # V1 맞닿음
    allowed = {frozenset(p) for p in [("MOUTH", "KB"), ("AIR", "AIRC"), ("AIRC", "M1C"), ("TA", "M1C"), ("TB", "M1C"), ("M1W", "M1C"), ("M1C", "M1E"),
                                      ("C3", "M1E")]}
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
    inner = {c for c, s in owner.items() if s not in ("MOUTH", "KB")}
    # V3
    reach = bfs(edge)
    unreached = sorted({owner[c] for c in inner if c not in reach})
    if unreached:
        problems.append(f"V3 바깥과 연결 안 됨: {unreached}")
    # V2
    kb = frozenset(c for c, s in owner.items() if s in ("MOUTH", "KB"))
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
    for sid in ("FRZ", "KIT", "TA", "TB", "M1C"):
        cs = [c for c, o in owner.items() if o == sid]
        if not any(c in r1 for c in cs):
            problems.append(f"V7 1단계: {sid} 바깥과 연결 안 됨")
        if any(c in r1b for c in cs):
            problems.append(f"V7 1단계: {sid} 킬박스 우회 경로 존재")
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
              conduit=CONDUIT, routes=routes,
              stats=dict(new_mined=total_new, mined_by_phase=dict(by_phase), filled=len(fill_cells), ore=dict(ore)),
              problems=problems)
    json.dump(bp, open(f"{out}/layout_v2.json", "w"), ensure_ascii=False, indent=1)
    sys.exit(1 if problems else 0)

if __name__ == "__main__":
    main()
