# Smart Office Life Agent

> "나의 업무 리듬과 개발 성향을 이해하고 함께 성장하는 반려 비서."

외부 API(카카오 맵/버스, Google Calendar)와 사용자의 PC/브라우저 활동 데이터를 결합해 직장인의 업무 생산성을 높이고 멘탈 케어를 돕는 **Google ADK 2.0** 기반 에이전트.

## 아키텍처 두 트랙

| 경로 | 엔진 | 용도 |
|------|------|------|
| 탭 버튼 (상태/버스/길찾기/점심/일정) | `google.adk.Workflow` (Graph) | 단발 UI 액션 · 빠른 응답 |
| **대화창 (펫 탭)** | `google.adk.Workflow` (Graph) — `pet_agent` | LLM 라우터 + route별 Sub-agent + 캘린더 **비-LLM HITL** + 점심 **Tavily 맛집 검색** |

두 경로 모두 최종적으로 펫 EXP/스트레스 갱신 로직으로 수렴  
대화창은 `router_decide_node` → `router_finalize_node` → 도메인 에이전트 → (필요 시) `hitl` / `restaurant_search` → `post_process_node` → `pet_care_node`  
라우터는 `src/agent/router.py`에 의도가 명확하면 LLM·의도 확인 HITL Pass

### 펫 채팅 그래프: Sub-agent 와 Node

`pet_chat_workflow` (`src/agent/pet_agent.py`)는 **Sub-agent(ADK `Agent`)** 와 **Node(일반 워크플로 노드)** 를 같은 `google.adk.Workflow` 엣지로 묶어서 활용

| 구분 | 역할 | 코드 위치 |
|------|------|-------------|
| **Sub-agent** | LLM + `FunctionTool` 등으로 사용자 질문에 라우터가 고른 route 문자열과 `Agent.name` 이 같아야 `pet_agent`의 `_ROUTE_TO_AGENT` 매핑 | `bus_agent`, `lunch_agent`, `calendar_agent`, `navigation_agent`, `wellness_coach`, `general_chat_agent` |
| **공통 Node** | 입력 정규화·보상 정책·DB 반영·최종 메시지. LLM 없음. | `init_node`, `post_process_node`, `pet_care_node`, `end_node` |
| **라우터 Node** | 의도 분류·(선택) 의도 확인 HITL·최종 route 확정. | `router_decide_node`, `router_finalize_node` |
| **도메인 Node** | 점심 추첨·캘린더 알림 등 `RequestInput` / `ctx.state` 만 사용 (비-LLM). Sub-agent 출력을 입력으로 받음 | `lunch_hitl.py`, `calendar_hitl.py`, `lunch_restaurant.py` |

- **`post_process_node`** 는 route·HITL 상태만 보고 EXP/stress 숫자를 정한 뒤, 응답 텍스트까지 **`AgentOutput`** 한 덩어리 종합
- **`pet_care_node`** 는 `AgentOutput`을 받아 펫 상태 갱신
- 버스 **`ask_user_tool`** 은 Sub-agent 툴 안에서 `src/agent/hitl.py` 의 **`GetInput`**(interrupt/재개) 패턴을 쓴다. 점심·캘린더 HITL과는 구현이 다르다. #################################### 이 부분 확인 필요

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

# 2) PostgreSQL 컨테이너 기동
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
| `desktop` (기본) | `--mode desktop --user-id 1` | **pywebview(WKWebView) 기반 네이티브 창.** 브라우저 탭이 아니라 독립 앱 창, 옵션: `--on-top` (항상 위), `--frameless` (타이틀바 제거), `--width/--height`. |
| `web` | `--mode web --user-id 1` | FastAPI 위젯을 브라우저 탭으로 연다. pywebview 없이도 동작. |
| `scheduler` | `--mode scheduler` | APScheduler 로 시스템 모니터/버스 알림/펫 스트레스 decay 를 주기 실행. |
| `seed` | `--mode seed --channel C123` | 테스트 사용자 주입. |
| `init-db` | `--mode init-db` | 스키마/테이블 보장. |

### 펫 대화창 에이전트 구조 (Router + Sub-agent + Node)
- 위젯 하단 **대화** 탭은 `pet_chat_workflow` (`google.adk.Workflow`) 그래프로 동작한다. 위 표의 **Sub-agent / Node** 조합으로 엣지가 정의된다.
- 라우터 (`src/agent/router.py`):
  - 메시지에 버스·점심·일정·길찾기·웰니스 등 **키워드/역명 패턴**이 맞으면 `_keyword_route`로 route를 바로 정하고, 이 경우 `router_decide_node`가 **`RequestInput`(의도 확인)** 을 받지 않음
  - 그 외에는 `router_decide_node`가 LLM(genai JSON)으로 후보 route를 정한 뒤, 사용자에게 추정 route 확인을 요청
  - `router_finalize_node`는 HITL 재개 입력을 받아 최종 route를 확정 짧은 긍정(예: 네, 응, ok, accept)이면 추정 route를 그대로 쓰고, 아니면 키워드 재시도 후 필요 시 LLM으로 재분류
- 도메인 분기:
  - `bus_agent` / `wellness_coach` / `navigation_agent` / `general_chat_agent` 는 각 에이전트 실행 후 바로 `post_process_node` (`navigation_agent` 는 카카오맵 웹 길찾기 링크 등).
  - `lunch_agent` → `lunch_draw_node` (HITL 없이 즉시 추첨) → `lunch_restaurant_search_node` (Tavily MCP로 회사 근처 맛집 검색) → `post_process_node`.
  - `calendar_agent` → `calendar_reminder_node`(HITL 또는 패스스루) → `calendar_finalize_node` → `post_process_node`.
- 공통 종료 체인:
  - `post_process_node` 에서 route별 보상 정책 계산
  - `pet_care_node` 에서 EXP/stress DB 반영
  - `end_node` 에서 최종 사용자 메시지 반환

## 4. 아키텍처 (Chat — Sub-agent + Node Workflow)

```mermaid
flowchart TB
  START([START]) --> init[init_node]
  init --> rdec[router_decide_node<br/>키워드 또는 LLM]
  rdec --> rfin[router_finalize_node<br/>HITL 생략 가능]
  rfin --> fork{route별 agent}
  fork --> lunch[lunch_agent]
  fork --> cal[calendar_agent]
  fork --> other[bus / wellness / navigation / general]
  lunch --> ld[lunch_draw_node<br/>즉시 추첨]
  ld --> lrs[lunch_restaurant_search_node<br/>Tavily 검색]
  lrs --> pp[post_process_node]
  cal --> cr[calendar_reminder_node<br/>HITL or passthrough]
  cr --> cfin[calendar_finalize_node]
  cfin --> pp
  other --> pp
  pp --> care[pet_care_node]
  care --> endn([end_node])
```

- 다이어그램에서 `router_decide_node` → `router_finalize_node` 는 항상 이어지지만, 키워드 fast-path일 때는 decide 단계에서 **의도 확인 `RequestInput` 없이** finalize 로 넘어간다.