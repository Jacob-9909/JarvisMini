"""Google Calendar API 래퍼.

`google-api-python-client` 는 optional extra 로 분리되어 있어 import 실패
시 자동으로 mock 응답을 반환한다. 실제 사용 시:

    pip install 'smart-office-life-agent[google]'
    export GOOGLE_CALENDAR_TOKEN_PATH=/path/to/token.json
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

try:  # optional import
    from googleapiclient.discovery import build  # type: ignore
    from google.oauth2.credentials import Credentials  # type: ignore

    _GCAL_AVAILABLE = True
except Exception:
    _GCAL_AVAILABLE = False


def _service() -> Optional[Any]:
    if not _GCAL_AVAILABLE:
        return None
    token_path = os.getenv("GOOGLE_CALENDAR_TOKEN_PATH")
    if not token_path or not os.path.exists(token_path):
        logger.debug("GOOGLE_CALENDAR_TOKEN_PATH not configured")
        return None
    creds = Credentials.from_authorized_user_file(token_path)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


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
            out.append({"summary": ev.get("summary", "(제목 없음)"), "start": start})
        return out
    except Exception as e:
        logger.warning("GCal API failed (%s) → mock", e)
        return _mock_events(now, until)


def _mock_events(now: datetime, until: datetime) -> List[Dict[str, Any]]:
    return [
        {"summary": "팀 스탠드업", "start": (now + timedelta(minutes=30)).isoformat()},
        {"summary": "스프린트 리뷰", "start": (now + timedelta(hours=2)).isoformat()},
    ]
