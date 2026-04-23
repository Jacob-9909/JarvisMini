"""컴팩트 웹 위젯 — FastAPI 서버.

`python -m src.main --mode web --user-id 1` 로 실행하면
자동으로 브라우저가 열리고, 약 400×560 크기의 미니 위젯 창을 띄운다.

백그라운드에서 `SystemMonitor`(pynput 전역 클릭/키 + psutil)를 주기적으로
샘플링하여 `activity_logs` 저장 및 펫 EXP 반영 (`monitor_pipeline.run_monitor_tick_for_user`).

REST:
    GET  /                 — 위젯 HTML
    GET  /api/state        — 사용자/펫/활동 + **실시간** CPU·RAM
    POST /api/action       — {"action": "bus|directions|..."} 를 Graph Workflow 로 전달
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import threading
import time
import uuid
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.db.session import SessionLocal
from src.db.models import User, PetProfile, ActivityLog
from src.tools import bus_api, lunch_roulette
from src.tools.pet import Pet
from src.tools.monitor_pipeline import read_live_cpu_mem, run_monitor_tick_for_user
from src.tools.system_monitor import SystemMonitor
from src.workflow.agent import root_agent, WorkflowInput, CURRENT_WORKFLOW_INPUT

# --- Pet Chatbot (ADK 2.0 Graph Workflow + domain agents) ---
from src.schema.api import ActionBody, ChatBody, BusConfigBody, UserProfileBody
from src.agent.pet_agent import pet_agent, CURRENT_CHAT_INPUT
from src.schema.chat import ChatWorkflowInput

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


CHAT_APP_NAME = "smart_office_pet"
DEFAULT_WIDTH = 420
DEFAULT_HEIGHT = 600
DEFAULT_TITLE = "Smart Office Pet"


REQUEST_INPUT_FC_NAME = "adk_request_input"


def _event_to_sse(event: Any) -> Optional[Dict[str, Any]]:
    """ADK Event → 프론트엔드가 이해하기 쉬운 SSE payload.

    - text      : LLM 의 텍스트 응답 (partial 이면 스트리밍 토큰)
    - tool_call : sub-agent 혹은 tool 호출 시작
    - tool_result: 도구 결과 요약
    - transfer  : sub-agent 로 전이
    - interrupt : HITL(RequestInput) 발생. 다음 요청은 function_response 로 와야 함
    """
    author = getattr(event, "author", None) or "model"
    content = getattr(event, "content", None)
    partial = bool(getattr(event, "partial", False))
    turn_complete = bool(getattr(event, "turn_complete", False))

    if content is not None and getattr(content, "parts", None):
        texts: list[str] = []
        for p in content.parts:
            fc = getattr(p, "function_call", None)
            if fc and getattr(fc, "name", None):
                # RequestInput(HITL) 은 function_call 로 포장되어 나오므로 별도 이벤트로 분기.
                if fc.name == REQUEST_INPUT_FC_NAME:
                    args = dict(getattr(fc, "args", {}) or {})
                    iid = getattr(fc, "id", None) or args.get("interrupt_id")
                    return {
                        "type": "interrupt",
                        "author": author,
                        "interrupt_id": iid,
                        "message": args.get("message", ""),
                        "response_schema": args.get("response_schema"),
                    }
                return {
                    "type": "tool_call",
                    "author": author,
                    "tool": fc.name,
                    "args": dict(getattr(fc, "args", {}) or {}),
                }
            fr = getattr(p, "function_response", None)
            if fr and getattr(fr, "name", None):
                resp = getattr(fr, "response", None)
                short = str(resp)[:280]
                return {
                    "type": "tool_result",
                    "author": author,
                    "tool": fr.name,
                    "response_preview": short,
                }
            t = getattr(p, "text", None)
            if t:
                texts.append(t)
        if texts:
            return {
                "type": "text",
                "author": author,
                "text": "".join(texts),
                "partial": partial,
                "turn_complete": turn_complete,
            }

    actions = getattr(event, "actions", None)
    transfer = getattr(actions, "transfer_to_agent", None) if actions else None
    if transfer:
        return {"type": "transfer", "author": author, "to": transfer}

    return None




def _profile_complete(user: User) -> bool:
    """필수 개인정보가 채워졌는지 (위젯 최초 진입 게이트)."""
    if not (user.display_name or "").strip():
        return False
    if not (user.gender or "").strip():
        return False
    if user.age is None or user.age < 1 or user.age > 120:
        return False
    if not (user.job_role or "").strip():
        return False
    if not (user.dev_tendency or "").strip():
        return False
    if user.company_lat is None or user.company_lng is None:
        return False
    try:
        lat = float(user.company_lat)
        lng = float(user.company_lng)
    except (TypeError, ValueError):
        return False
    # 대한민국 대략 범위 (실수 방지)
    if not (33.0 <= lat <= 39.5 and 124.0 <= lng <= 132.5):
        return False
    return True


def _create_app(default_user_id: int) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 전역 입력·CPU/RAM 폴링 워커를 먼저 올려 /api/state 가 0만 보이지 않게 함
        SystemMonitor.instance().start()

        # --- Chat Runner 싱글톤 (Graph Workflow 기반 라우팅) ---
        from google.adk.runners import Runner
        from google.adk.plugins import LoggingPlugin, ReflectAndRetryToolPlugin

        from google.adk.sessions import InMemorySessionService
        session_service = InMemorySessionService()
        plugins = [
            LoggingPlugin(name="pet_logging"),
            ReflectAndRetryToolPlugin(max_retries=2),
        ]
        chat_runner = Runner(
            app_name=CHAT_APP_NAME,
            node=pet_agent,
            session_service=session_service,
            plugins=plugins,
            auto_create_session=True,
        )
        app.state.chat_runner = chat_runner
        logger.info("Pet chat Runner ready (workflow=%s)", pet_agent.name)

        interval = float(os.getenv("WEB_MONITOR_INTERVAL_SECONDS", "30"))
        enabled = os.getenv("WEB_BACKGROUND_MONITOR", "true").lower() in (
            "1",
            "true",
            "yes",
        )
        task: Optional[asyncio.Task] = None
        if enabled:

            async def _monitor_loop() -> None:
                while True:
                    try:
                        await asyncio.to_thread(run_monitor_tick_for_user, default_user_id)
                    except Exception as e:
                        logger.warning("background monitor tick: %s", e)
                    await asyncio.sleep(interval)

            task = asyncio.create_task(_monitor_loop())
            logger.info(
                "Web background monitor ON (user_id=%s, every %ss). "
                "Set WEB_BACKGROUND_MONITOR=false if scheduler also runs monitor.",
                default_user_id,
                interval,
            )
        try:
            yield
        finally:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            try:
                await chat_runner.close()
            except Exception as e:  # noqa: BLE001
                logger.debug("chat_runner close: %s", e)

    app = FastAPI(
        title="Smart Office Life Agent Widget",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse(
            "widget.html",
            {
                "request": request,
                "user_id": default_user_id,
                "kakao_maps_js_app_key": os.getenv("KAKAO_MAPS_JAVASCRIPT_APP_KEY", ""),
            },
        )

    @app.get("/api/state")
    async def api_state(user_id: int = default_user_id):
        """세션을 닫기 전에 ORM 필드를 모두 읽는다. close() 이후 접근하면 만료·Detached 로
        이전 커밋 값이 보이거나 오류가 날 수 있다."""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="user not found")
            pet = db.query(PetProfile).filter(PetProfile.user_id == user_id).first()
            last_log = (
                db.query(ActivityLog)
                .filter(ActivityLog.user_id == user_id)
                .order_by(ActivityLog.ts.desc())
                .first()
            )
            profile_ok = _profile_complete(user)

            live_cpu, live_mem = await asyncio.to_thread(read_live_cpu_mem)

            pet_obj = Pet(
                species=pet.species if pet else "egg",
                nickname=pet.nickname if pet else None,
            )
            mood = pet.mood if pet else "neutral"
            exp_to_next = (
                max(0, pet.level * 100 - pet.exp) if pet else 100
            )
            return JSONResponse(
                {
                    "user": {
                        "id": user.id,
                        "display_name": user.display_name or user.username,
                        "gender": user.gender,
                        "age": user.age,
                        "job_role": user.job_role,
                        "dev_tendency": user.dev_tendency,
                        "company_lat": user.company_lat,
                        "company_lng": user.company_lng,
                        "company_address": user.company_address,
                        "bus_stop_id": user.bus_stop_id,
                        "bus_route_id": user.bus_route_id,
                        "profile_complete": profile_ok,
                    },
                    "pet": {
                        "species": pet.species if pet else "egg",
                        "nickname": pet.nickname if pet else None,
                        "level": pet.level if pet else 1,
                        "exp": pet.exp if pet else 0,
                        "exp_to_next": exp_to_next,
                        "mood": mood,
                        "stress": pet.stress if pet else 0,
                        "frame": pet_obj.frame(mood),
                        "say": pet_obj.say(mood),
                    },
                    "activity": {
                        "ts": last_log.ts.isoformat() if last_log else None,
                        "cpu": last_log.cpu_percent if last_log else 0.0,
                        "mem": last_log.mem_percent if last_log else 0.0,
                        "tabs": last_log.active_tabs if last_log else 0,
                        "clicks": last_log.click_count if last_log else 0,
                        "keys": last_log.key_count if last_log else 0,
                        "exp_gain_sample": last_log.computed_exp_gain if last_log else 0,
                        "stress_delta_sample": last_log.computed_stress_delta if last_log else 0,
                        "note": "클릭/키는 전역(pynput) 구간 합산, 탭은 확장 연동 전까지 0일 수 있음",
                    },
                    "live": {
                        "cpu_percent": live_cpu,
                        "mem_percent": live_mem,
                    },
                }
            )
        finally:
            db.close()

    @app.get("/api/bus/stations")
    async def api_bus_stations(q: str = "", limit: int = 10):
        """정류소명 또는 ARS(5자리) 검색 → 정류소 목록."""
        items, hint = await bus_api.search_stations(q, limit=limit)
        return JSONResponse({"items": items, "hint": hint or None})

    @app.get("/api/bus/routes")
    async def api_bus_routes(ars_id: str = ""):
        """정류소를 경유하는 노선 목록."""
        items = await bus_api.get_routes_by_station(ars_id)
        return JSONResponse({"items": items})

    @app.get("/api/lunch/history")
    async def api_lunch_history(user_id: int = default_user_id):
        return JSONResponse({"items": lunch_roulette.recent_picks(user_id)})

    @app.delete("/api/lunch/history")
    async def api_lunch_history_clear(user_id: int = default_user_id):
        cleared = lunch_roulette.clear_history(user_id)
        return JSONResponse({"ok": True, "cleared": cleared})

    @app.post("/api/user/profile")
    async def api_user_profile(body: UserProfileBody, user_id: int = default_user_id):
        """표시 이름·성별·나이·직군·개발 성향·회사 좌표 저장."""
        dn = (body.display_name or "").strip()
        if not dn:
            raise HTTPException(status_code=400, detail="display_name required")
        if body.age < 1 or body.age > 120:
            raise HTTPException(status_code=400, detail="invalid age")
        lat, lng = float(body.company_lat), float(body.company_lng)
        if not (33.0 <= lat <= 39.5 and 124.0 <= lng <= 132.5):
            raise HTTPException(
                status_code=400,
                detail="company_lat/lng out of range (Korea approximate)",
            )
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="user not found")
            user.display_name = dn
            user.gender = (body.gender or "").strip() or None
            user.age = body.age
            user.job_role = (body.job_role or "").strip() or None
            user.dev_tendency = (body.dev_tendency or "").strip() or None
            user.company_lat = lat
            user.company_lng = lng
            # JSON 에서 null 이 오면 주소 비우기까지 반영해야 함 (if is not None 이면 갱신 안 됨)
            user.company_address = (body.company_address or "").strip() or None
            db.commit()
            db.refresh(user)
            return JSONResponse(
                {
                    "ok": True,
                    "profile_complete": _profile_complete(user),
                }
            )
        finally:
            db.close()

    @app.post("/api/user/bus")
    async def api_user_bus(body: BusConfigBody, user_id: int = default_user_id):
        """버스 정류장 / 노선 번호를 사용자 프로필에 저장."""
        stop_id = (body.stop_id or "").strip() or None
        route_id = (body.route_id or "").strip() or None
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="user not found")
            user.bus_stop_id = stop_id
            user.bus_route_id = route_id
            db.commit()
            return JSONResponse(
                {"ok": True, "stop_id": user.bus_stop_id, "route_id": user.bus_route_id}
            )
        finally:
            db.close()

    # =============================================================
    #  Pet Chatbot — ADK 2.0 Supervisor + Sub-agents (LLM routing)
    # =============================================================
    @app.post("/api/chat")
    async def api_chat(body: ChatBody, user_id: int = default_user_id):
        """같은 session_id 로 재요청하면 Runner 세션(대화 이벤트)을 이어간다.

        - 첫 메시지는 body.session_id 가 비어 있으면 서버가 새 id 를 만들어 SSE 로 내려준다.
        - ``body.function_response`` 가 있으면 이 턴은 HITL interrupt 재개 요청으로
          해석되어 Runner 에 function_response Content 를 ``new_message`` 로 전달한다.
        """
        import json as _json
        from fastapi.responses import StreamingResponse
        from google.genai import types as genai_types
        from google.adk.workflow.utils._workflow_hitl_utils import (
            create_request_input_response,
            wrap_response,
        )

        chat_runner = app.state.chat_runner
        raw_sid = (body.session_id or "").strip()
        is_resume = body.function_response is not None
        if is_resume and not raw_sid:
            # 세션 없이 재개하면 Runner 가 빈 세션으로 돌아가 점심 HITL 등이 끊긴다.
            async def _resume_err():
                err = {
                    "type": "error",
                    "message": (
                        "확인 단계(HITL)를 이어하려면 대화 session_id 가 필요해요. "
                        "대화 탭을 한 번 나갔다 들어오거나, 점심을 처음부터 다시 요청해 주세요."
                    ),
                }
                yield f"event: error\ndata: {_json.dumps(err, ensure_ascii=False)}\n\n"
                yield "event: done\ndata: {}\n\n"

            return StreamingResponse(_resume_err(), media_type="text/event-stream")

        session_id = raw_sid if raw_sid else uuid.uuid4().hex

        async def _stream():
            yield f"event: session\ndata: {_json.dumps({'session_id': session_id})}\n\n"
            token = None
            try:
                if is_resume:
                    fr_payload = body.function_response  
                    fr_part = create_request_input_response(
                        interrupt_id=fr_payload.id,
                        response=wrap_response(fr_payload.response),
                    )
                    new_message = genai_types.Content(role="user", parts=[fr_part])
                    async for event in chat_runner.run_async(
                        user_id=str(user_id),
                        session_id=session_id,
                        new_message=new_message,
                    ):
                        data = _event_to_sse(event)
                        if data is not None:
                            yield f"event: {data['type']}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"
                else:
                    wf_input = ChatWorkflowInput(user_id=user_id, message=body.message)
                    token = CURRENT_CHAT_INPUT.set(wf_input)
                    async for event in chat_runner.run_async(
                        user_id=str(user_id),
                        session_id=session_id,
                        state_delta={"user_id": user_id, "input": wf_input.model_dump()},
                    ):
                        data = _event_to_sse(event)
                        if data is not None:
                            yield f"event: {data['type']}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"
            except Exception as e:  # noqa: BLE001
                logger.exception("chat runner error")
                err = {"type": "error", "message": str(e)}
                yield f"event: error\ndata: {_json.dumps(err, ensure_ascii=False)}\n\n"
            finally:
                if token is not None:
                    CURRENT_CHAT_INPUT.reset(token)
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(_stream(), media_type="text/event-stream")

    @app.post("/api/action")
    async def api_action(body: ActionBody, user_id: int = default_user_id):
        from google.adk import Runner
        from google.adk.sessions import InMemorySessionService

        runner = Runner(
            node=root_agent,
            session_service=InMemorySessionService(),
            auto_create_session=True,
        )
        action_result: Dict[str, Any] = {}
        wf_input = WorkflowInput(
            user_id=user_id, action=body.action, payload=body.payload
        )
        token = CURRENT_WORKFLOW_INPUT.set(wf_input)
        try:
            async for event in runner.run_async(
                user_id=str(user_id),
                session_id=f"web_{body.action}",
                state_delta={"input": wf_input.model_dump()},
            ):
                output = getattr(event, "output", None)
                if isinstance(output, dict) and "care" in output:
                    action_result = output
        except Exception as e:
            logger.exception("workflow failed")
            raise HTTPException(status_code=500, detail=str(e)) from e
        finally:
            CURRENT_WORKFLOW_INPUT.reset(token)
        return JSONResponse(action_result)

    return app


def _open_browser(url: str) -> None:
    try:
        webbrowser.open_new(url)
    except Exception:
        webbrowser.open(url)


async def run_web(user_id: int, host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    app = _create_app(user_id)

    def _delayed_open() -> None:
        import time

        time.sleep(0.8)
        _open_browser(f"http://{host}:{port}/")

    threading.Thread(target=_delayed_open, daemon=True).start()

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def _find_free_port(preferred: int = 8765) -> int:
    """선호 포트가 비어있으면 그대로, 아니면 자동 할당."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run_uvicorn_in_background(
    user_id: int, host: str, port: int
) -> "threading.Thread":
    """uvicorn 을 별도 스레드에서 기동."""
    import uvicorn

    app = _create_app(user_id)

    def _serve() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
            lifespan="on",
            loop="asyncio",
        )
        server = uvicorn.Server(config)
        try:
            loop.run_until_complete(server.serve())
        finally:
            loop.close()

    t = threading.Thread(target=_serve, name="uvicorn-web", daemon=True)
    t.start()
    return t


def _wait_until_ready(host: str, port: int, timeout_s: float = 10.0) -> bool:
    """서버 listen 준비까지 대기."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.25)
            try:
                s.connect((host, port))
                return True
            except OSError:
                time.sleep(0.15)
    return False


def _fallback_browser(user_id: int, host: str, port: int) -> None:
    """pywebview 실패 시 브라우저 폴백."""
    import uvicorn

    app = _create_app(user_id)
    url = f"http://{host}:{port}/"

    def _open_later() -> None:
        time.sleep(0.8)
        _open_browser(url)

    threading.Thread(target=_open_later, daemon=True).start()
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    asyncio.run(server.serve())


def run_desktop(
    user_id: int,
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    title: str = DEFAULT_TITLE,
    on_top: bool = False,
    frameless: bool = False,
) -> None:
    """pywebview 로 위젯을 네이티브 창에 띄운다."""
    try:
        import webview
    except ImportError:
        logger.warning(
            "pywebview 미설치로 브라우저 폴백. `uv add pywebview` 후 desktop 모드를 사용하세요."
        )
        return _fallback_browser(user_id, host, port)

    port = _find_free_port(port)
    _run_uvicorn_in_background(user_id, host, port)

    if not _wait_until_ready(host, port, timeout_s=10.0):
        logger.error("웹 서버 준비 실패로 브라우저 폴백")
        return _fallback_browser(user_id, host, port)

    url = f"http://{host}:{port}/"
    logger.info("Opening desktop window → %s", url)

    class _DesktopApi:
        """widget.html → pywebview.api.open_external(url) 로 외부 링크 열기."""

        def open_external(self, target_url: str) -> bool:
            if not target_url or not isinstance(target_url, str):
                return False
            if not target_url.lower().startswith(("http://", "https://")):
                return False
            try:
                webbrowser.open(target_url, new=2)
                return True
            except Exception:
                logger.exception("open_external failed: %s", target_url)
                return False

    webview.create_window(
        title=title,
        url=url,
        width=width,
        height=height,
        resizable=True,
        frameless=frameless,
        # True면 본문 아무 곳이나 잡아도 창이 움직여 UI 조작이 불편함.
        # 창 이동은 HTML titlebar 의 data-pywebview-drag-region 만 사용한다.
        easy_drag=False,
        on_top=on_top,
        background_color="#0f111a",
        js_api=_DesktopApi(),
    )

    debug = os.getenv("DESKTOP_DEBUG", "").lower() in ("1", "true", "yes")
    try:
        webview.start(debug=debug)
    except Exception:
        logger.exception("pywebview 실행 실패 → 브라우저 폴백")
        _fallback_browser(user_id, host, port)
    finally:
        logger.info("Desktop window closed.")
