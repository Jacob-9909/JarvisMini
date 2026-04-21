# Smart Office Life Agent

> "나의 업무 리듬과 개발 성향을 이해하고 함께 성장하는 반려 비서."

외부 API(카카오 맵/버스, Google Calendar)와 사용자의 PC/브라우저 활동 데이터를 결합해 직장인의 업무 생산성을 높이고 멘탈 케어를 돕는 **Google ADK 2.0** 기반 에이전트.

## 아키텍처 두 트랙

| 경로 | 엔진 | 용도 |
|------|------|------|
| 탭 버튼 (상태/버스/카페/점심/일정) | `google.adk.Workflow` (Graph) | deterministic UX · 빠른 응답 |
| **대화창 (펫 탭)** | `google.adk.Agent` Supervisor + `PlanReActPlanner` + 6 Sub-agents | 자연어 라우팅 · 복합 질의 |

두 경로 모두 동일한 `PetCare` 로직에 수렴해 펫 EXP/스트레스를 갱신한다. Supervisor 에는 `before_model_callback` 으로 실시간 CPU/RAM/펫 상태가 주입되며 (자기상태 인지), `after_tool_callback` 으로 툴 호출 시마다 보상이 반영된다.

---

## 1. 시스템 요구사항
- Python 3.11+
- `uv` (권장) 또는 pip
- Docker & Docker Compose (PostgreSQL 기반)
- macOS 에서 `pynput` 사용 시 **접근성(Accessibility) 권한** 필요

## 2. 빠른 시작

```bash
# 1) env 복사
cp .env.example .env

# 2) PostgreSQL 컨테이너 기동 (스키마 init 스크립트 자동 적용)
docker-compose -f docker/docker-compose.yaml up -d db

# 3) Python 의존성
uv sync

# 4) DB 스키마/테이블 생성
uv run python -m src.main --mode init-db

# 5) 테스트 사용자 주입 + 데스크톱 위젯 실행
uv run python -m src.main --mode seed
uv run python -m src.main --mode desktop --user-id 1
# 브라우저 탭으로 띄우고 싶을 때만
uv run python -m src.main --mode web --user-id 1
```

## 3. 실행 모드
| 모드 | 명령 | 설명 |
|------|------|------|
| `desktop` (기본) | `uv run python -m src.main --mode desktop --user-id 1` | **pywebview(WKWebView) 기반 네이티브 창.** 브라우저 탭이 아니라 독립 앱 창처럼 뜬다. 옵션: `--on-top` (항상 위), `--frameless` (타이틀바 제거), `--width/--height`. |
| `web` | `uv run python -m src.main --mode web --user-id 1` | FastAPI 위젯을 브라우저 탭으로 연다. pywebview 없이도 동작. |
| `scheduler` | `uv run python -m src.main --mode scheduler` | APScheduler 로 시스템 모니터/버스 알림/펫 스트레스 decay 를 주기 실행. |
| `seed` | `uv run python -m src.main --mode seed --channel C123` | 테스트 사용자 주입. |
| `init-db` | `uv run python -m src.main --mode init-db` | 스키마/테이블 보장. |

### 펫 대화창 (ADK 2.0 Supervisor + Sub-agents)
- 위젯 하단 **대화** 탭을 누르면 `google.adk.Agent`(Gemini 2.5 Flash) Supervisor 가 직접 응답한다.
- 내부 구성:
  - `PlanReActPlanner` — 복합 질의를 Plan-Act-Observe 로 분해
  - Sub-agents: `bus_agent` / `cafe_agent` / `lunch_agent` / `calendar_agent` / `wellness_coach` / `coding_mentor`
  - Tools: 기존 `src/tools/*` 를 `FunctionTool` 로 래핑 (`src/agent/tools.py`)
  - **PostgreSQL 기반 `SessionService`, `MemoryService`** — 세션·이벤트·장기 기억을 `agent_state.adk_*` 테이블에 영속화
  - Plugins: `LoggingPlugin`, `ReflectAndRetryToolPlugin` (툴 실패 시 자기 복구)
- REST
  - `POST /api/chat?user_id=1` (body: `{message}`) → **SSE 스트리밍** (`text` / `tool_call` / `tool_result` / `transfer` / `error` / `done`)
  - 현재는 stateless 모드로, 요청마다 신규 세션으로 처리한다.
- **필수 환경변수**: `GOOGLE_API_KEY` (Google AI Studio). Vertex 사용 시 `GOOGLE_GENAI_USE_VERTEXAI=TRUE` + GCP 프로젝트.

### 첫 실행 프로필 (온보딩)
- DB `auth.users`에 **표시 이름·성별·나이·직군·개발 성향·회사 위도·경도**가 비어 있거나, 좌표가 대한민국 대략 범위를 벗어나면 위젯이 **전 화면 폼**을 띄우고, 저장 전까지 다른 기능을 쓰지 못한다.
- 저장 API: `POST /api/user/profile` (본문 JSON). 응답의 `profile_complete`와 `GET /api/state`의 `user.profile_complete`로 완료 여부를 판별한다.
- 타이틀바 **프로필** 버튼으로 나중에 다시 수정할 수 있다.

### 웹 위젯: 전역 클릭·CPU·RAM
- 위젯 서버가 떠 있는 동안 **백그라운드**에서 `WEB_MONITOR_INTERVAL_SECONDS`(기본 30초)마다 전역 마우스 클릭·키 입력(`pynput`)과 CPU/RAM을 샘플링해 `activity_logs`에 저장하고, 같은 규칙으로 **펫 EXP**를 올린다. 위젯 안만 클릭한 게 아니라 **OS 전체** 입력이 반영된다.
- `/api/state`의 **CPU·RAM 숫자는 실시간(psutil)** 이고, `activity` 블록은 **마지막으로 저장된 구간**의 클릭/키/탭/구간 EXP이다.
- **macOS**에서는 `pynput`이 동작하려면 터미널/IDE에 **접근성(Accessibility)** 권한이 필요하다. 권한이 없으면 클릭·키 카운트는 0에 가깝게 나올 수 있다.
- **`uv run python -m src.scheduler`**(또는 Docker `app` 서비스)와 **동시에** 웹 백그라운드 모니터를 켜면 동일 사용자에게 EXP가 **이중 적용**될 수 있다. 스케줄러만 쓸 때는 `.env`에 `WEB_BACKGROUND_MONITOR=false` 로 끄는 것을 권장한다.

### 웹 위젯을 항상 위에 띄우는 팁
- Chrome/Edge: 위젯 주소를 연 뒤 `⋮` → **Cast, save and share → Install page as app** 으로 프레임리스 창처럼 사용 가능.
- macOS: 위젯 창 우클릭 → 서비스/시스템 단축키로 'Keep on Top' 계열 확장(`Rectangle`, `Amphetamine` 등) 과 조합.

### 기능 구현 상태 (요약)
| 기능 | 코드 | 비고 |
|------|------|------|
| 상태 보드 | ✅ | DB의 펫·사용자 요약 |
| 버스 / 카페 / 점심 / 캘린더 / 펫 인터랙션 | ✅ | `bus_api`·`map_api` 등은 **키 없으면 mock**; 버스는 `KAKAO_BUS_BASE_URL` 프록시 필요할 수 있음 |
| 카페·점심 | ⚠️ | `auth.users`에 **회사 좌표**(`company_lat`/`lng`)가 있어야 의미 있음 |
| 버스 | ⚠️ | `bus_stop_id` 등 프로필 필드 + (선택) Slack |
| 구글 캘린더 | ⚠️ | `pip install '.[google]'` + `GOOGLE_CALENDAR_TOKEN_PATH` 없으면 mock 일정 |

ADK Web UI 로도 실행 가능:
```bash
uv run adk web src/workflow
# 이후 smart_office_workflow 선택 → state_delta 로 {"input": {"user_id": 1, "action": "bus"}} 입력
```

## 4. 아키텍처 (Graph Workflow)

```
START ─▶ init_node ─▶ router_node
                        │
       ┌────────────────┼──────────────────┐
       ▼                ▼                   ▼
 dashboard_node   system_monitor_node    end_node
       │                │
       └────────────────┘
                ▼
          pet_care_node ─▶ end_node
```

- **Router Node**: 입력 `action` 으로 Dashboard / System Monitor / End 로 분기.
- **Dashboard Node**: bus / cafe / lunch_roulette / calendar / pet_interact / status 등 단발성 UI 액션.
- **System Monitor Node**: 워커 스레드로 누적된 psutil(RAM/CPU) + pynput(클릭/키) + 브라우저 탭 수를 한 번에 드레인.
- **Pet Care Node**: 경험치/스트레스/레벨업/진화 규칙 적용 후 `agent_state.pet_profile` 업데이트.
- **Node Execution Log**: 모든 노드 실행이 `workflow.node_execution` 에 밀리초 단위로 기록되어 성능 튜닝 가능.

## 5. PostgreSQL 스키마

- `auth.users` — 사용자 프로필 (직군/성향/회사 좌표/버스 정류장·노선/Slack 채널 등)
- `agent_state.pet_profile` — 펫 종류/레벨/EXP/mood/stress
- `agent_state.activity_logs` — Monitor 가 남기는 스냅샷 (EXP/stress 계산치 포함)
- `workflow.node_execution` — 노드별 실행 시간/경로/payload
- `workflow.memory_context` — ADK 2.0 Memory 의 단기/장기 컨텍스트 저장

스키마는 `docker/init-schemas.sql` 로 초기화되고, `src/db/session.py::init_db()` 가 `CREATE SCHEMA IF NOT EXISTS` 로 이중 안전망을 제공한다.

## 6. 업무 활동량(Activity) → 펫 성장 규칙

| 지표 | EXP | Stress |
|------|-----|--------|
| 클릭+타이핑 ≥ 200 | +20 | — |
| 클릭+타이핑 ≥ 50  | +8  | — |
| 무거운 IDE 실행 중 | +10 | — |
| 활성 탭 ≥ 20     | —   | +15 |
| 활성 탭 ≥ 12     | —   | +5 |
| 메모리 ≥ 90%      | —   | +10 |
| 메모리 ≥ 75%      | —   | +3 |

- `stress ≥ 70` → `stressed` / `≥ 40` → `tired` / 집중 신호 → `focused`.
- 레벨 임계치: `level * 100` EXP. 레벨업/진화 시 Slack 채널로 알림 가능.

## 7. 외부 API 연동

| 툴 | 파일 | 키 미설정 시 |
|----|------|--------------|
| Kakao Local (카페/식당) | `src/tools/map_api.py` | mock 데이터 반환 |
| Google Maps JS (카페 탭 미니맵) | `src/ui/templates/widget.html` | 키 미설정 시 목록만 표시 |
| 서울시 정류소 도착정보 (공공데이터포털) | `src/tools/bus_api.py` | 키 미설정/호출 실패 시 mock 폴백 |
| 점심 룰렛 | `src/tools/lunch_roulette.py` | 가상 카테고리 |
| Google Calendar | `src/tools/calendar_api.py` | mock 일정 2건 |
| Slack 알림 | `src/tools/notifier.py` | no-op |

> 오픈 API 가 없는 환경에서도 즉시 실행 가능하도록 전 구간에 graceful fallback 이 들어 있다.

### 버스 API 사용법 (서울시 공공데이터포털)

`src/tools/bus_api.py` 는 서울특별시 공공데이터포털의 **정류소정보조회 서비스**
(`getStationByUidItem`) 와 **정류소명 검색**(`getStationByName`) 을 래핑한다.
정류소 번호(ARS ID, 5자리) 하나로 해당 정류소의 모든 경유 노선 도착 예정 정보
(최대 2대, 혼잡도 / 저상 / 만차 / 막차 / 최종 정류소 등) 를 한 번에 가져온다.

위젯 **정류소 검색**에는 짧은 이름(예: `강남역`)만 넣어도 되고, 긴 문장이면
앱이 잡어를 걷어내고 쉼표 뒤 지명 등 여러 후보로 `getStationByName` 을 순서대로 호출한다
(완전한 자연어 이해는 아니며, 공공 API 부분 일치 검색에 맞춘 전처리다).

1. [공공데이터포털](https://www.data.go.kr) 회원가입 후
   "서울특별시_정류소정보조회 서비스" 를 **활용신청** → 개발계정 자동 승인(보통 즉시).
2. 마이페이지 → **내 API** 에서 해당 서비스의 인증키를 복사해 `.env` 에 저장:
   - **인증키(Decoding)** 을 넣는 것을 권장한다.
   - **인증키(Encoding)** 만 있어도 된다. 앱이 내부에서 디코딩한 뒤 요청 시 한 번만 인코딩한다.
   ```
   SEOUL_BUS_API_KEY=여기에_붙여넣기
   ```
3. `BUS_USE_MOCK=0` 인지 확인한다. 키가 비어 있으면 mock 이 나온다.
4. `auth.users` 의 `bus_stop_id` 에 ARS 번호(예: `12121`)를 저장.
   (웹 위젯의 **버스 탭**에서 직접 입력·저장 가능.)
5. `bus_route_id` 에는 `7211` 같이 노선명을 지정하면 해당 노선만 필터링하여
   표시한다. `7211,146` 처럼 쉼표로 복수 지정 가능. 비우면 전체 노선.
6. 완전 오프라인 모드: `.env` 에 `BUS_USE_MOCK=1`

### 카페 탭 Google Maps 시각화 (옵션)

카페 탭의 500m 반경 Kakao Local 결과 위에 Google Maps 미니맵이 오버레이된다.

1. [Google Cloud Console](https://console.cloud.google.com) 에서 **Maps JavaScript API** 활성화 → API 키 발급.
2. `.env` 에 키 저장:
   ```
   GOOGLE_MAPS_API_KEY=AIza...
   GOOGLE_MAPS_MAP_ID=         # (선택) Map ID 를 쓰면 Cloud Styles 적용, 비우면 내장 다크 스타일
   ```
3. 위젯 상단바에서 앱을 열고 **카페 탭**을 누르면 회사 좌표 중심의 지도와 카페 마커가 표시된다.
   목록을 클릭하면 해당 마커로 이동/InfoWindow가 열린다.
4. 키가 비어 있으면 지도는 숨겨지고 기존 목록만 표시된다 (Kakao 데이터는 그대로 사용).

> 보안: 운영 환경에서는 반드시 Cloud Console의 **API 키 제한**(HTTP referrer 또는 IP) 을 설정한다.
> 데스크톱 `pywebview` 실행 시에는 `http://127.0.0.1:*` referrer 허용이 필요하다.

응답 스키마(프론트 위젯이 소비) — `arrivals[i]`::

    { minutes, seat, stop_count, route, direction, final_stop,
      bus_type ("저상"/"굴절"/""), congestion ("여유"/"보통"/"혼잡"),
      is_full, is_last, is_arrived, message, route_type, interval_min }

> 참고: Encoding 키만 있을 때는 이중 인코딩을 피하기 위해 앱에서 `unquote` 후
> 요청한다. Decoding 키를 쓰면 그대로 한 번만 인코딩된다.

## 8. 브라우저 탭 개수 주입

브라우저 확장 프로그램이 현재 창의 탭 개수를 WebSocket/IPC 로 프로세스에 전달하면, 다음처럼 주입할 수 있다.

```python
from src.tools.system_monitor import SystemMonitor

def count_tabs() -> int:
    ...  # 확장에서 전달받은 최신 값
    return 17

SystemMonitor.instance().set_tab_count_provider(count_tabs)
```

## 9. 트러블슈팅
- **`pynput` 훅이 카운트되지 않음** → macOS 시스템 설정 > 개인정보 보호 > 접근성에 터미널/IDE를 추가.
- **DB 연결 실패** → `.env` 의 `POSTGRES_HOST` 가 컨테이너 네트워크(`db`) 혹은 로컬(`127.0.0.1`)과 일치하는지 확인.
- **Kakao API 429/403** → `KAKAO_REST_KEY` 쿼터 초과. fallback mock 이 반환된다.
