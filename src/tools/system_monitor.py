"""System Monitor.

별도 워커 스레드에서 돌아가며 PC 리소스와 마우스/키보드 입력을 누적 집계한다.
ADK Graph 의 System Monitor Node 는 `get_snapshot_and_reset()` 만 호출하면
블로킹 없이 즉시 현재 누적치를 가져올 수 있다.

외부 의존성(pynput)은 OS 권한 이슈가 있을 수 있어 import 실패 시
자동으로 훅 없이도 동작하도록 graceful-fallback 을 제공한다.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional

import psutil

try:  # pynput 은 macOS 접근성 권한이 없으면 import 자체가 실패하지 않지만 Listener.start() 가 실패할 수 있음
    from pynput import mouse, keyboard

    _PYNPUT_AVAILABLE = True
except Exception:
    _PYNPUT_AVAILABLE = False

logger = logging.getLogger(__name__)

HEAVY_PROCESS_NAMES = {
    "idea",
    "intellij",
    "pycharm",
    "code",
    "cursor",
    "chrome",
    "firefox",
    "docker",
    "python",
    "node",
}


@dataclass
class _Counters:
    click_count: int = 0
    key_count: int = 0
    screen_active_sec: int = 0
    last_reset: datetime = field(default_factory=datetime.utcnow)


class SystemMonitor:
    """싱글턴으로 운용하는 백그라운드 모니터."""

    _instance: Optional["SystemMonitor"] = None
    _singleton_lock = threading.Lock()

    def __init__(self, sampling_interval: float = 1.0):
        self.sampling_interval = sampling_interval
        self._counters = _Counters()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._mouse_listener = None
        self._keyboard_listener = None
        self._tab_count_provider = lambda: 0  # 브라우저 확장에서 websocket 등으로 주입 가능
        self._latest_cpu = 0.0
        self._latest_mem = 0.0

    @classmethod
    def instance(cls) -> "SystemMonitor":
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = SystemMonitor()
            return cls._instance

    def set_tab_count_provider(self, fn) -> None:
        """브라우저 확장 프로그램이 콜백으로 현재 탭 개수를 주입할 수 있게 함."""
        self._tab_count_provider = fn

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._start_hooks()
        self._worker = threading.Thread(
            target=self._run_loop, name="system-monitor-worker", daemon=True
        )
        self._worker.start()
        logger.info("SystemMonitor started (pynput=%s)", _PYNPUT_AVAILABLE)

    def stop(self) -> None:
        self._stop_event.set()
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
        if self._keyboard_listener:
            try:
                self._keyboard_listener.stop()
            except Exception:
                pass
        if self._worker:
            self._worker.join(timeout=2.0)
        logger.info("SystemMonitor stopped")

    # -- hooks --
    def _start_hooks(self) -> None:
        if not _PYNPUT_AVAILABLE:
            logger.warning("pynput unavailable; click/key hooks will be no-op")
            return
        try:
            def _on_click(x, y, button, pressed):
                if pressed:
                    with self._lock:
                        self._counters.click_count += 1

            def _on_press(key):  # noqa: ARG001
                with self._lock:
                    self._counters.key_count += 1

            self._mouse_listener = mouse.Listener(on_click=_on_click)
            self._keyboard_listener = keyboard.Listener(on_press=_on_press)
            self._mouse_listener.start()
            self._keyboard_listener.start()
        except Exception as e:  # macOS 접근성 권한 미부여 등
            logger.warning("Failed to start pynput listeners: %s", e)

    # -- polling worker --
    def _run_loop(self) -> None:
        # psutil.cpu_percent 첫 호출은 캘리브레이션용
        psutil.cpu_percent(interval=None)
        while not self._stop_event.is_set():
            try:
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory().percent
                with self._lock:
                    self._latest_cpu = cpu
                    self._latest_mem = mem
                    self._counters.screen_active_sec += int(self.sampling_interval)
            except Exception as e:
                logger.debug("sampling error: %s", e)
            self._stop_event.wait(self.sampling_interval)

    # -- top processes --
    @staticmethod
    def _top_processes(limit: int = 5) -> List[Dict[str, Any]]:
        procs: List[Dict[str, Any]] = []
        for p in psutil.process_iter(attrs=["pid", "name", "memory_percent", "cpu_percent"]):
            try:
                info = p.info
                if not info.get("name"):
                    continue
                procs.append(
                    {
                        "pid": info["pid"],
                        "name": info["name"],
                        "mem": round(info.get("memory_percent") or 0.0, 2),
                        "cpu": round(info.get("cpu_percent") or 0.0, 2),
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: x["mem"], reverse=True)
        return procs[:limit]

    @staticmethod
    def _has_heavy_ide(procs: List[Dict[str, Any]]) -> bool:
        return any(
            any(h in (p["name"] or "").lower() for h in HEAVY_PROCESS_NAMES) for p in procs
        )

    def get_latest_cpu_mem(self) -> tuple[float, float]:
        """폴링 워커가 마지막으로 갱신한 CPU·RAM (%). UI 실시간 표시용."""
        with self._lock:
            return float(self._latest_cpu), float(self._latest_mem)

    def _build_snapshot(self, *, reset: bool) -> Dict[str, Any]:
        with self._lock:
            snap = {
                "ts": datetime.utcnow(),
                "click_count": self._counters.click_count,
                "key_count": self._counters.key_count,
                "screen_active_sec": self._counters.screen_active_sec,
                "cpu_percent": self._latest_cpu,
                "mem_percent": self._latest_mem,
            }
            if reset:
                self._counters = _Counters()

        top = self._top_processes()
        try:
            tabs = int(self._tab_count_provider() or 0)
        except Exception:
            tabs = 0
        snap["top_processes"] = top
        snap["active_tabs"] = tabs
        snap["heavy_ide"] = self._has_heavy_ide(top)
        return snap

    def peek_snapshot(self) -> Dict[str, Any]:
        """현재 누적치를 반환하되 **카운터를 리셋하지 않는다** (LLM 진단용)."""
        return self._build_snapshot(reset=False)

    def get_snapshot_and_reset(self) -> Dict[str, Any]:
        """현재 누적치를 반환하고 counter 를 리셋."""
        return self._build_snapshot(reset=True)
