# 아스테라스 산악 요새 (RimWorld 1.6 · 전 DLC)

세이브 `아스테라스 (철인 모드)`를 해독해, 실제 지형 위에 설계한 기지 계획입니다.

| 파일 | 내용 |
|---|---|
| `docs/01_research.md` | 1단계 자료조사: 세이브에서 해독한 사실 + 위키 수치 (설계의 유일한 근거) |
| `docs/02_design.md` | 2단계 설계 v2: 배치, 내정·방어·스트레스 테스트, 단계별 순서 |
| `blueprint/layout_v2.json` | 모든 공간·문·되메움·야외 시설 좌표 + 검증 수치 |
| `blueprint/validation_report.txt` | 검증 스크립트 출력 원문 |
| `blueprint/core_v2.png`, `overview_v2.png` | 실제 지형 위 배치도 |
| `planner/index.html` | 인터랙티브 설계도 (단계·레이어 토글, 좌표 검사기) |

## 재현

세이브 파일 경로를 `SAVE`라 할 때, 작업 폴더에서:

```bash
python3 -I tools/parse_things.py "$SAVE"        # → things.pkl (맵 위 모든 사물)
python3 -I tools/decode_grids.py "$SAVE"        # → grids.pkl (지형·지붕·광물 그리드)
python3 -I tools/render_terrain.py              # → arr.pkl (단축 해시 → 이름 매핑), map.png
python3 -I tools/parse_pawns.py "$SAVE"         # 정착민 스킬·특성
python3 -I tools/design.py arr.pkl things.pkl blueprint          # 배치 정의 + 7항목 검증 (실패 시 종료코드 1)
python3 -I tools/render.py arr.pkl blueprint/layout_v2.json blueprint/core_v2.png 106 162 194 222 12
python3 -I tools/export_web.py arr.pkl things.pkl blueprint/layout_v2.json blueprint/web_data.json
python3 -I tools/build_planner.py                # → planner/index.html
```

`tools/shorthash.py`는 RimWorld의 def 단축 해시(`GenText.StableStringHash` 기반)를 계산해 세이브의 압축 그리드 값을 지형·광물 이름으로 되돌립니다.

## 검증 항목 (`tools/design.py`)
- V1 겹침·벽 누락·문이 두 공간을 잇는지
- V2 킬박스를 막으면 외부→내부 경로가 0 (단일 출입구)
- V3 모든 내부 공간이 외부와 연결
- V4 용도 없이 남는 굴착 칸 0
- V5 야외 시설이 암반·산지붕 위에 없음, 전선 경로가 암반을 통과하지 않음
- V6 입구 터널 외 모든 내부 공간이 100% 두꺼운 산 지붕 아래
- V7 1단계 공사 중간 상태에서도 단일 출입구 유지
