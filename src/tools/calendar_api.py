"""Google Calendar API 래퍼.

실연동 절차:
  1) GCP에서 Calendar API 사용 설정 + OAuth **데스크톱** 클라이언트 JSON 다운로드
  2) ``GOOGLE_CALENDAR_CLIENT_SECRETS_PATH`` 에 그 JSON 경로 설정 (로컬만, Git 커밋 금지)
  3) 한 번만: ``uv run python -m src.tools.calendar_oauth`` 로 브라우저 로그인 → 토큰 저장
  4) (선택) ``GOOGLE_CALENDAR_TOKEN_PATH`` — 비우면 ``<프로젝트>/data/google_calendar_token.json`` 이 있으면 자동 사용

토큰 만료 시 ``refresh_token`` 이 있으면 자동 갱신 후 같은 경로에 다시 저장한다.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    """``src/tools/calendar_api.py`` 기준 프로젝트 루트."""
    return Path(__file__).resolve().parents[2]


def _calendar_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:  
        return ZoneInfo("UTC")


def _event_start_local(s: str, tz: ZoneInfo) -> datetime:
    """Google Calendar event start 문자열 → ``tz`` 기준 시각."""
    s = (s or "").strip()
    if not s:
        return datetime.now(tz)
    if "T" in s:
        raw = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if raw.tzinfo is None:
            raw = raw.replace(tzinfo=timezone.utc)
        return raw.astimezone(tz)
    d = date.fromisoformat(s[:10])
    return datetime.combine(d, datetime.min.time(), tzinfo=tz)


# 일정 조회에 필요한 최소 범위. 일정 생성까지 하려면 calendar.events 등으로 확장.
GCAL_SCOPES: Tuple[str, ...] = (
    "https://www.googleapis.com/auth/calendar.readonly",
)

try:  # google-* 는 pyproject 메인 의존성
    from google.auth.transport.requests import Request  # type: ignore
    from google.oauth2.credentials import Credentials  # type: ignore
    from googleapiclient.discovery import build  # type: ignore

    _GCAL_AVAILABLE = True
except Exception:  
    Request = None  # type: ignore[misc, assignment]
    Credentials = None  # type: ignore[misc, assignment]
    build = None  # type: ignore[misc, assignment]
    _GCAL_AVAILABLE = False


def _token_path() -> Optional[str]:
    """환경 변수 경로가 없거나 파일이 없으면 ``<repo>/data/google_calendar_token.json`` 을 본다.

    OAuth 스크립트(``calendar_oauth``)는 ``GOOGLE_CALENDAR_TOKEN_PATH`` 가 비었을 때
    기본으로 이 경로에 저장하는데, 런타임은 예전 코드처럼 env 만 보면 파일을 못 찾아
    항상 mock 이 되는 버그가 있었다.
    """
    env_p = (os.getenv("GOOGLE_CALENDAR_TOKEN_PATH") or "").strip()
    candidates: list[Path] = []
    if env_p:
        candidates.append(Path(env_p).expanduser())
    default_repo = _repo_root() / "data" / "google_calendar_token.json"
    candidates.append(default_repo)
    cwd_default = Path.cwd() / "data" / "google_calendar_token.json"
    if cwd_default.resolve() != default_repo.resolve():
        candidates.append(cwd_default)

    seen: set[str] = set()
    for c in candidates:
        try:
            key = str(c.resolve())
        except OSError:
            key = str(c)
        if key in seen:
            continue
        seen.add(key)
        if c.is_file():
            logger.debug("Google Calendar token file: %s", key)
            return key

    logger.info(
        "Google Calendar: 토큰 파일 없음 → mock 일정. "
        "env GOOGLE_CALENDAR_TOKEN_PATH=%r, 기본 경로=%s",
        env_p or None,
        default_repo,
    )
    return None


def _load_credentials() -> Optional[Any]:
    """token.json 기반 Credentials. 만료 시 refresh 후 파일에 다시 쓴다."""
    if not _GCAL_AVAILABLE or Credentials is None or Request is None:
        return None
    token_path = _token_path()
    if not token_path or not os.path.isfile(token_path):
        logger.debug("GOOGLE_CALENDAR_TOKEN_PATH 없거나 파일 없음 → mock")
        return None
    try:
        creds = Credentials.from_authorized_user_file(token_path, GCAL_SCOPES)
    except Exception as e:  
        logger.warning("캘린더 토큰 로드 실패: %s", e)
        return None
    if creds.valid:
        return creds
    try:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            Path(token_path).write_text(creds.to_json(), encoding="utf-8")
            return creds
    except Exception as e:  
        logger.warning("캘린더 토큰 갱신 실패: %s", e)
    logger.warning(
        "캘린더 인증이 유효하지 않습니다. `uv run python -m src.tools.calendar_oauth` 로 재발급하세요."
    )
    return None


def _service() -> Optional[Any]:
    if not _GCAL_AVAILABLE or build is None:
        return None
    creds = _load_credentials()
    if creds is None:
        return None
    try:
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:  
        logger.warning("Calendar build 실패: %s", e)
        return None


def upcoming_events(hours: int = 4) -> List[Dict[str, Any]]:
    svc = _service()
    now = datetime.now(timezone.utc)
    until = now + timedelta(hours=hours)
    if svc is None:
        return _mock_events(now, until)
    try:
        events = (
            svc.events()
            .list(
                calendarId="primary",
                timeMin=now.isoformat(),
                timeMax=until.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        out: List[Dict[str, Any]] = []
        for ev in events.get("items", []):
            start = ev["start"].get("dateTime", ev["start"].get("date"))
            end = ev["end"].get("dateTime", ev["end"].get("date"))
            out.append(
                {
                    "summary": ev.get("summary", "(제목 없음)"),
                    "start": start,
                    "end": end,
                    "location": ev.get("location") or "",
                }
            )
        return out
    except Exception as e:  
        logger.warning("GCal API failed (%s) → mock", e)
        return _mock_events(now, until)


def week_bundle(tz_name: Optional[str] = None) -> Dict[str, Any]:
    """이번 주(월 00:00 ~ 다음 주 월 00:00 직전, ``tz_name``) 일정 + UI용 ``day_index``(월=0).

    위젯 주간 그리드는 ``events[].day_index`` 로 열을 나눈다.
    ``GOOGLE_CALENDAR_TZ`` (기본 ``Asia/Seoul``) 로 주 경계를 잡는다.
    """
    name = (tz_name or os.getenv("GOOGLE_CALENDAR_TZ") or "Asia/Seoul").strip() or "Asia/Seoul"
    tz = _calendar_tz(name)
    now = datetime.now(tz)
    monday = now.date() - timedelta(days=now.weekday())
    week_start = datetime.combine(monday, datetime.min.time(), tzinfo=tz)
    week_end_excl = week_start + timedelta(days=7)
    sunday = monday + timedelta(days=6)

    svc = _service()
    if svc is None:
        events = _mock_week_events(week_start)
    else:
        try:
            raw = (
                svc.events()
                .list(
                    calendarId="primary",
                    timeMin=week_start.isoformat(),
                    timeMax=week_end_excl.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = []
            for ev in raw.get("items", []):
                start = ev["start"].get("dateTime", ev["start"].get("date"))
                end = ev["end"].get("dateTime", ev["end"].get("date"))
                dt0 = _event_start_local(str(start), tz)
                day_index = max(0, min(6, (dt0.date() - monday).days))
                events.append(
                    {
                        "summary": ev.get("summary", "(제목 없음)"),
                        "start": start,
                        "end": end,
                        "location": ev.get("location") or "",
                        "day_index": day_index,
                    }
                )
        except Exception as e:  
            logger.warning("GCal week list failed (%s) → mock", e)
            events = _mock_week_events(week_start)

    day_labels = []
    wk = ["월", "화", "수", "목", "금", "토", "일"]
    for i in range(7):
        d = monday + timedelta(days=i)
        day_labels.append(f"{wk[i]} {d.month}/{d.day}")

    return {
        "events": events,
        "week": {
            "tz": name,
            "start_date": monday.isoformat(),
            "end_date": sunday.isoformat(),
            "day_labels": day_labels,
        },
    }


def _mock_week_events(week_start: datetime) -> List[Dict[str, Any]]:
    evs = [
        {
            "summary": "팀 스탠드업",
            "start": (week_start + timedelta(days=1, hours=10)).isoformat(),
            "end": (week_start + timedelta(days=1, hours=11)).isoformat(),
            "location": "",
            "day_index": 1,
        },
        {
            "summary": "스프린트 리뷰",
            "start": (week_start + timedelta(days=3, hours=15)).isoformat(),
            "end": (week_start + timedelta(days=3, hours=16)).isoformat(),
            "location": "",
            "day_index": 3,
        },
    ]
    return evs


def _mock_events(now: datetime, _until: datetime) -> List[Dict[str, Any]]:
    return [
        {
            "summary": "팀 스탠드업",
            "start": (now + timedelta(minutes=30)).isoformat(),
            "end": (now + timedelta(hours=1)).isoformat(),
            "location": "",
        },
        {
            "summary": "스프린트 리뷰",
            "start": (now + timedelta(hours=2)).isoformat(),
            "end": (now + timedelta(hours=3)).isoformat(),
            "location": "",
        },
    ]
