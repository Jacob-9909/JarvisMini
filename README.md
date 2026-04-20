# BookChecker

ADK 2.0 기반 지능형 예약 에이전트.
Playwright를 이용한 웹 크롤링 및 Telegram/Slack 연동을 통한 Human-In-The-Loop(HITL) 워크플로우를 지원합니다.

## 시스템 요구사항
- Python 3.10+
- uv
- Docker (for PostgreSQL)

## 설치 및 준비
1. `.env.example`을 `.env`로 복사하고 설정 값을 채워줍니다.
```bash
cp .env.example .env
```

2. 데이터베이스를 실행합니다.
```bash
docker-compose -f docker/docker-compose.yaml up -d
```

3. 의존성을 설치합니다.
```bash
uv sync
```

4. Playwright 브라우저를 설치합니다.
```bash
uv run playwright install
```

## 시스템 구조
- **Init_Node**: 환경 변수 및 설정 로딩.
- **Auth_Node**: Playwright를 이용한 대상 사이트 자동 로그인.
- **Scan_Node**: 잔여 슬롯/티켓 크롤링.
- **Match_Node**: 사용자의 선호도(날짜, 구역)에 맞게 가중치를 계산.
- **Human_Input_Node**: (선택적) 모호한 선택지나 결제 직전에 사용자에게 텔레그램으로 승인을 요청하며 워크플로우 중단.
- **Action_Node**: 예약 확정 및 노티 통보.

## 실행
### 개발 및 인터랙티브 테스트 (ADK Web UI)
로컬 개발 및 워크플로우 테스트를 위해 ADK Web UI를 시작합니다:
```bash
uv run adk web agents
```
이후 `bookchecker_workflow`를 선택하여 실행 흐름을 확인하고, `Human_Input_Node`에서 JSON 형태로 값을 입력하여 워크플로우를 재개할 수 있습니다.

### 프로덕션 상시 가동 / 배치 실행 (Scheduler)
지수 백오프(Exponential Backoff) 및 주기적인 배치가 포함된 스케줄러를 실행합니다:
```bash
uv run python -m src.scheduler
```

