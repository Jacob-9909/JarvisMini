"""선택적 Slack 알림. 토큰 미설정이면 조용히 no-op."""

from __future__ import annotations

import os
import logging

import aiohttp

logger = logging.getLogger(__name__)


class SlackNotifier:
    def __init__(self) -> None:
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.base_url = "https://slack.com/api/chat.postMessage"

    async def send_message(self, channel_id: str, text: str) -> bool:
        if not self.bot_token or not channel_id:
            logger.debug("Slack disabled; skip message: %s", text[:80])
            return False

        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        payload = {"channel": channel_id, "text": text}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, headers=headers, json=payload) as resp:
                    data = await resp.json()
                    if not data.get("ok"):
                        logger.warning("Slack API error: %s", data.get("error"))
                        return False
                    return True
        except Exception as e:
            logger.warning("Slack send error: %s", e)
            return False
