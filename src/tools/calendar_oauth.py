"""Google Calendar OAuth — 최초 1회(또는 토큰 폐기 후) 브라우저로 로그인해 token 을 저장한다.

환경 변수:
  GOOGLE_CALENDAR_CLIENT_SECRETS_PATH  GCP 콘솔에서 받은 OAuth 클라이언트 JSON (앱 유형: 데스크톱)
  GOOGLE_CALENDAR_TOKEN_PATH          (선택) 저장할 token 경로. 비우면 ./data/google_calendar_token.json

실행:
  uv run python -m src.tools.calendar_oauth

주의: client_secret*.json 과 token 파일은 Git 에 올리지 말 것 (.gitignore 참고).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.tools.calendar_api import GCAL_SCOPES

logger = logging.getLogger(__name__)


def main() -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    secrets = (os.getenv("GOOGLE_CALENDAR_CLIENT_SECRETS_PATH") or "").strip()
    if not secrets:
        logger.error(
            "GOOGLE_CALENDAR_CLIENT_SECRETS_PATH 가 설정되지 않았습니다. "
            ".env 에 OAuth 클라이언트 JSON 경로를 넣으세요."
        )
        return 1
    if not Path(secrets).is_file():
        logger.error("클라이언트 비밀 파일이 없습니다: %s", secrets)
        return 1

    token_path = (os.getenv("GOOGLE_CALENDAR_TOKEN_PATH") or "").strip()
    if not token_path:
        token_path = str(Path("data") / "google_calendar_token.json")
    out = Path(token_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        logger.error(
            "google-auth-oauthlib 가 없습니다. 프로젝트 루트에서 `uv sync` 후 다시 실행하세요."
        )
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(secrets, list(GCAL_SCOPES))
    creds = flow.run_local_server(port=0)
    out.write_text(creds.to_json(), encoding="utf-8")
    logger.info("토큰 저장: %s", out.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
