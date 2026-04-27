"""Tavily 검색 MCP 서버 (FastMCP, stdio).

`tavily-mcp@latest` (npx Node 패키지) 의존을 끊기 위한 자체 구현.

도구:
- ``tavily_search(query, max_results=5, search_depth="basic", topic="general",
  include_domains=None, exclude_domains=None, time_range=None, country=None)``

실행:
    uv run python -m src.mcp_servers.tavily_server         # stdio
    uv run python -m src.mcp_servers.tavily_server --http  # HTTP(127.0.0.1:8930) 디버그용

환경변수:
    TAVILY_API_KEY (필수)
    TAVILY_MCP_HOST / TAVILY_MCP_PORT (HTTP 모드 옵션)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any, Dict, List, Literal, Optional

from dotenv import load_dotenv
from fastmcp import FastMCP
from tavily import TavilyClient

load_dotenv()

logger = logging.getLogger(__name__)

SearchDepth = Literal["basic", "advanced", "fast", "ultra-fast"]
Topic = Literal["general", "news", "finance"]
TimeRange = Literal["day", "week", "month", "year"]

mcp = FastMCP(
    name="jarvis-tavily",
    instructions=(
        "Tavily 웹 검색 MCP 서버. tavily_search 1개 도구를 노출한다. "
        "쿼리는 한국어/영어 모두 가능. 결과는 results 배열(title/url/content/score) 과 "
        "옵션 answer 를 포함한다."
    ),
)


def _client() -> TavilyClient:
    key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("TAVILY_API_KEY 가 비어 있어 Tavily 검색을 호출할 수 없습니다.")
    return TavilyClient(api_key=key)


@mcp.tool
def tavily_search(
    query: str,
    max_results: int = 3,
    search_depth: SearchDepth = "basic",
    topic: Topic = "general",
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    time_range: Optional[TimeRange] = None,
    country: Optional[str] = None,
    include_answer: bool = True,
) -> Dict[str, Any]:
    """Tavily 웹 검색을 수행해 정리된 결과를 반환.

    Args:
        query: 검색어. 자연어/키워드 모두 가능.
        max_results: 결과 개수 (1~20). 기본 5.
        search_depth: ``basic`` | ``advanced`` | ``fast`` | ``ultra-fast``.
        topic: ``general`` | ``news`` | ``finance``.
        include_domains: 화이트리스트 도메인 목록.
        exclude_domains: 블랙리스트 도메인 목록.
        time_range: ``day`` | ``week`` | ``month`` | ``year``.
        country: ISO 2자리 국가 코드 (예: ``KR``). 지역 결과 강조.
        include_answer: Tavily 의 LLM 요약 답변 포함 여부.
    """
    q = (query or "").strip()
    if not q:
        return {"error": "empty_query", "results": []}

    try:
        n = max(1, min(int(max_results), 5))
    except (TypeError, ValueError):
        n = 5

    try:
        raw = _client().search(
            query=q,
            search_depth=search_depth,
            topic=topic,
            max_results=n,
            include_domains=list(include_domains) if include_domains else None,
            exclude_domains=list(exclude_domains) if exclude_domains else None,
            time_range=time_range,
            country=country,
            include_answer=include_answer,
        )
    except Exception as exc:
        msg = str(exc)
        code = "quota_exceeded" if "usage limit" in msg.lower() or "quota" in msg.lower() else "tavily_request_failed"
        logger.error("tavily search failed [%s]: %s", code, msg)
        return {"error": code, "message": msg, "results": []}

    results = []
    for item in (raw.get("results") or [])[:n]:
        results.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "content": item.get("content"),
                "score": item.get("score"),
                "published_date": item.get("published_date"),
            }
        )

    return {
        "query": q,
        "answer": raw.get("answer"),
        "results": results,
        "response_time": raw.get("response_time"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Jarvis Tavily MCP server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="HTTP 모드로 실행 (기본은 stdio).",
    )
    parser.add_argument(
        "--host", default=os.getenv("TAVILY_MCP_HOST", "127.0.0.1")
    )
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("TAVILY_MCP_PORT", "8930"))
    )
    args = parser.parse_args()

    if args.http:
        logger.info("Tavily MCP HTTP 모드: http://%s:%s", args.host, args.port)
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        # stdio: 모든 로그는 stderr 로만 (프로토콜 채널 오염 방지).
        logging.basicConfig(level=logging.INFO, stream=sys.stderr)
        mcp.run()


if __name__ == "__main__":
    main()
