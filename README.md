# 아스테라스 산악 요새 (RimWorld 1.6 · 전 DLC)

세이브 `아스테라스 (철인 모드)`를 해독해, 실제 지형 위에 설계한 기지 계획입니다.

| 파일 | 내용 |
|---|---|
| `docs/01_research.md` | 1단계 자료조사: 세이브에서 해독한 사실 + 위키 수치 (설계의 유일한 근거) |
| `docs/02_design.md` | 설계 v3: 킬존 9층, 전투 교리, 배치, 검증, 단계별 순서 |
| `docs/03_enemy_ai.md` | 적 AI 조사(1.6 디컴파일 소스 요약) + 공병·돌파 경로 모의 실험 |
| `blueprint/layout_v3.json` | 모든 공간·문·되메움·킬존 요소·야외 시설 좌표 + 검증 수치 |
| `blueprint/validation_report.txt` | 검증 스크립트 출력 원문 (12개 검사) |
| `blueprint/raid_sim_report.txt`, `raid_sim_v3.json` | 공병·돌파 경로 모의 실험 결과 |
| `blueprint/drop_sim_report.txt`, `drop_sim_v3.json` | 드롭포드(중앙 투하) 착륙 가능성 분석 |
| `blueprint/standoff_report.txt`, `standoff_v3.json` | 사선·엄폐 분석: 미로 안 저격 자리, 사로 엄폐, 사수 엄폐 |
| `blueprint/core_v3.png`, `killzone_v3.png`, `overview_v3.png` | 실제 지형 위 배치도 |
| `planner/index.html` | 인터랙티브 설계도 (단계·레이어·사선 토글, 좌표 검사기) |

## 재현

세이브 파일 경로를 `SAVE`라 할 때, 작업 폴더에서:

```bash
python3 -I tools/parse_things.py "$SAVE"        # → things.pkl (맵 위 모든 사물)
python3 -I tools/decode_grids.py "$SAVE"        # → grids.pkl (지형·지붕·광물 그리드)
python3 -I tools/render_terrain.py              # → arr.pkl (단축 해시 → 이름 매핑), map.png
python3 -I tools/parse_pawns.py "$SAVE"         # 정착민 스킬·특성
python3 -I tools/design.py arr.pkl things.pkl blueprint          # 배치 정의 + 12항목 검증 (실패 시 종료코드 1)
python3 -I tools/raid_sim.py arr.pkl things.pkl blueprint/layout_v3.json blueprint/raid_sim_v3.json   # 공병·돌파 경로 모의 실험
python3 -I tools/drop_sim.py arr.pkl blueprint/layout_v3.json blueprint/drop_sim_v3.json      # 드롭포드 착륙 분석
python3 -I tools/standoff_sim.py arr.pkl blueprint/layout_v3.json blueprint/standoff_v3.json > blueprint/standoff_report.txt   # 사선·엄폐
python3 -I tools/render.py arr.pkl blueprint/layout_v3.json blueprint/core_v3.png 106 162 194 224 12
python3 -I tools/render.py arr.pkl blueprint/layout_v3.json blueprint/killzone_v3.png 136 162 192 200 20
python3 -I tools/render.py arr.pkl blueprint/layout_v3.json blueprint/overview_v3.png 92 112 238 226 6
python3 -I tools/export_web.py arr.pkl things.pkl blueprint/layout_v3.json blueprint/web_data.json
python3 -I tools/build_planner.py                # → planner/index.html
```

`tools/shorthash.py`는 RimWorld의 def 단축 해시(`GenText.StableStringHash` 기반)를 계산해 세이브의 압축 그리드 값을 지형·광물 이름으로 되돌립니다.

## 검증 항목 (`tools/design.py`)
- V1 겹침·벽 누락·문이 두 공간을 잇는지
- V2 킬존(미로+사로)을 막으면 외부→내부 경로가 0 (단일 출입구)
- V3 모든 내부 공간이 외부와 연결
- V4 용도 없이 남는 굴착 칸 0
- V5 야외 시설이 암반·산지붕 위에 없음, 전선 경로가 암반을 통과하지 않음
- V6 미로 진입 터널 외 모든 내부 공간이 100% 두꺼운 산 지붕 아래
- V7 1단계 공사 중간 상태에서도 단일 출입구 유지
- V8 킬존 층 순서 강제(방폭문 D1·근접 방어 문)
- V9 방폭문이 모두 열려도 사로→대기실·응급실·주 통로 직선 사선 0
- V10 사대 전 칸에서 입구 가시 + 사로 가시율
- V11 미로는 지름길 없는 외길
- V12 킬존(미로·모래주머니 앞 사로)에서 내부 공간까지 순수 암반 4칸 이상

## 적 AI 근거
`docs/03_enemy_ai.md`는 공개 디컴파일 저장소(RimWorld 1.6, ILSpy)를 읽고 클래스·메서드 이름과 수치만 요약했다. 소스 원문은 이 저장소에 포함하지 않는다.
