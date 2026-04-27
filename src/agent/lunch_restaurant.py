"""Lunch 추첨 후 회사 근처 맛집을 Tavily MCP 로 검색하는 노드.

흐름: lunch_draw_node → lunch_restaurant_search_node → post_process_node

회사 좌표/주소를 user 프로필에서 읽어 ``"<지역> 근처 <당첨 메뉴> 맛집"`` 쿼리로
사내 FastMCP 기반 ``src.mcp_servers.tavily_server`` 의 ``tavily_search`` 툴을
stdio 로 호출한다. 검색 결과 요약을 ``response`` 에 이어 붙여 다음 노드
(post_process)로 넘긴다.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from google.adk import Event
from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.workflow import node
from mcp import StdioServerParameters

from src.db.models import User
from src.db.session import SessionLocal

logger = logging.getLogger(__name__)

MODEL = os.getenv("MODEL", "gemini-2.5-flash")


def _build_tavily_toolset() -> McpToolset | None:
    """사내 FastMCP Tavily 서버(stdio) 를 ``tavily_search`` 만 노출해 연결."""
    api_key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not api_key:
        logger.warning("TAVILY_API_KEY 가 비어 있어 Tavily MCP 비활성화.")
        return None
    env = {**os.environ, "TAVILY_API_KEY": api_key}
    return McpToolset(
        connection_params=StdioServerParameters(
            command=sys.executable,
            args=["-m", "src.mcp_servers.tavily_server"],
            env=env,
        ),
        tool_filter=["tavily_search"],
    )


_tavily_toolset = _build_tavily_toolset()

restaurant_search_agent = Agent(
    name="lunch_restaurant_search_agent",
    model=MODEL,
    description="회사 근처 점심 메뉴 맛집을 웹 검색해 3~5곳을 한국어로 추려 제공한다.",
    instruction=(
        "너는 점심 맛집 큐레이터다.\n"
        "- 입력으로 ``메뉴``와 ``회사 위치(주소/지역명)``가 주어진다.\n"
        "- 반드시 `tavily_search` 툴을 1회 호출해 최신 정보를 가져와라. "
        "쿼리는 ``<회사 위치> <메뉴> 맛집`` 형태로 한국어로 작성한다.\n"
        "- 결과 중 회사 위치와 가까운 곳 위주로 3~5곳을 골라 한국어로 짧게 요약한다.\n"
        "- 각 항목은 ``- 가게명 — 한 줄 특징 (URL)`` 형식의 한 줄.\n"
        "- 검색 실패/결과 없음이면 그 사실만 한 줄로 알려라.\n"
        "- 추가 인사말/이모지/길게 늘어지는 설명 금지."
    ),
    tools=[_tavily_toolset] if _tavily_toolset else [],
    output_key="response",
    disallow_transfer_to_peers=True,
)


def _company_location(ctx) -> str:
    """state.user_id 로 회사 주소/좌표 라벨을 만든다."""
    try:
        uid = int(ctx.state.get("user_id") or 0)
    except Exception:
        uid = 0
    if not uid:
        return "회사 근처"
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == uid).first()
    finally:
        db.close()
    if not user:
        return "회사 근처"
    if user.company_address:
        return str(user.company_address)
    if user.company_lat is not None and user.company_lng is not None:
        return f"{user.company_lat:.5f},{user.company_lng:.5f}"
    return "회사 근처"


@node(name="lunch_restaurant_search_node", rerun_on_resume=True)
async def lunch_restaurant_search_node(ctx, node_input: Any):
    """추첨 결과 메뉴로 회사 근처 맛집을 Tavily MCP 검색."""
    winner = str(ctx.state.get("lunch_winner") or "").strip()
    status = str(ctx.state.get("pending_lunch_status") or "")
    prev_text = ""
    if isinstance(node_input, dict):
        prev_text = str(node_input.get("response") or "")

    # 추첨이 취소됐거나 winner 가 없으면 검색 스킵
    if status == "cancelled" or not winner or winner == "?":
        yield Event(
            output={
                "response": prev_text or "점심 추첨 취소.",
                "lunch_status": status or "cancelled",
            },
        )
        return

    if _tavily_toolset is None:
        yield Event(
            state={"lunch_restaurants_text": ""},
            output={
                "response": (
                    f"{prev_text}\n\n"
                    "🔎 Tavily API 키가 없어 맛집 검색을 건너뛰었습니다."
                ).strip(),
                "lunch_status": status or "accepted",
                "winner": winner,
            },
        )
        return

    location = _company_location(ctx)
    query = f"메뉴: {winner}\n회사 위치: {location}"

    try:
        result = await ctx.run_node(restaurant_search_agent, query)
    except Exception as exc:
        logger.warning("tavily restaurant search failed: %s", exc)
        result = None

    search_text = result if isinstance(result, str) else (str(result) if result else "")

    # 에이전트가 quota/error 관련 텍스트를 그대로 반환할 경우 노출 억제
    _quota_hints = ("usage limit", "quota", "초과", "upgrade", "contact support")
    if any(h in search_text.lower() for h in _quota_hints):
        logger.warning("Tavily quota exceeded — skipping restaurant text")
        search_text = ""

    if search_text:
        text = f"{prev_text}\n\n🍴 {location} 근처 {winner} 맛집:\n{search_text}".strip()
    else:
        text = prev_text.strip()

    yield Event(
        state={
            "lunch_restaurants_text": search_text,
            "lunch_restaurants_query": query,
        },
        output={
            "response": text,
            "lunch_status": status or "accepted",
            "winner": winner,
        },
    )


__all__ = ["lunch_restaurant_search_node", "restaurant_search_agent"]
