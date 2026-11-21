"""Run every COM call on one dedicated single-threaded-apartment (STA) thread.

SolidWorks interface pointers belong to the apartment that created them, and the MCP
server calls tools from arbitrary threads, so all SolidWorks work is funnelled through a
single worker thread.

A COM call that hangs (typically behind a modal SolidWorks dialog) cannot be cancelled
from Python. When a job overruns its timeout the worker marks its thread as stuck: later
jobs fail immediately with :class:`SolidWorksBusy` instead of each waiting a full timeout.
A fresh thread is only started once a short probe call succeeds again.
"""

from __future__ import annotations

import concurrent.futures as cf
import queue
import threading
from collections.abc import Callable
from typing import Any

DEFAULT_TIMEOUT = 120.0
PROBE_TIMEOUT = 5.0


class SolidWorksBusy(RuntimeError):
    """SolidWorks did not answer in time (busy, or a dialog is open)."""


def _com_init() -> None:
    try:
        import pythoncom
    except ImportError:  # non-Windows: plain thread, no COM
        return
    pythoncom.CoInitialize()


class _Thread:
    def __init__(self, on_start: Callable[[], Any] | None) -> None:
        self.jobs: queue.Queue = queue.Queue()
        self.ready = cf.Future()
        self.thread = threading.Thread(target=self._run, args=(on_start,), daemon=True)
        self.thread.start()

    def _run(self, on_start: Callable[[], Any] | None) -> None:
        _com_init()
        try:
            self.ready.set_result(on_start() if on_start else None)
        except BaseException as exc:
            self.ready.set_exception(exc)
        while True:
            item = self.jobs.get()
            if item is None:
                return
            fn, fut = item
            if not fut.set_running_or_notify_cancel():
                continue
            try:
                fut.set_result(fn())
            except BaseException as exc:
                fut.set_exception(exc)

    def submit(self, fn: Callable[[], Any]) -> cf.Future:
        fut: cf.Future = cf.Future()
        self.jobs.put((fn, fut))
        return fut

    def stop(self) -> None:
        self.jobs.put(None)


class StaWorker:
    """Serialises callables onto one STA thread with per-job timeouts.

    ``on_start`` runs first on every (re)started thread; its return value is passed to
    each job, so a job receives the connection that belongs to its own thread.
    ``probe`` runs on a throwaway thread to decide whether a stuck worker may restart.
    """

    def __init__(
        self,
        on_start: Callable[[], Any] | None = None,
        probe: Callable[[], Any] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        probe_timeout: float = PROBE_TIMEOUT,
    ) -> None:
        self._on_start = on_start
        self._probe = probe
        self._timeout = timeout
        self._probe_timeout = probe_timeout
        self._lock = threading.Lock()
        self._thread: _Thread | None = None
        self._stuck = False

    def _current(self) -> _Thread:
        with self._lock:
            if self._stuck:
                if not self._probe_ok():
                    raise SolidWorksBusy(
                        "SolidWorks đang bận hoặc đang mở một hộp thoại; "
                        "đóng hộp thoại trong SolidWorks rồi thử lại."
                    )
                self._stuck = False
                self._thread = None
            if self._thread is None:
                self._thread = _Thread(self._on_start)
            return self._thread

    def _probe_ok(self) -> bool:
        if self._probe is None:
            return False
        t = _Thread(None)
        try:
            t.submit(self._probe).result(timeout=self._probe_timeout)
            return True
        except Exception:
            return False
        finally:
            t.stop()

    def run(self, fn: Callable[[Any], Any], timeout: float | None = None) -> Any:
        """Run ``fn(context)`` on the worker thread and wait for its result."""
        t = self._current()
        limit = self._timeout if timeout is None else timeout
        try:
            ctx = t.ready.result(timeout=limit)
        except BaseException:
            # Startup failed (e.g. SolidWorks not open yet): start afresh next time.
            with self._lock:
                if self._thread is t:
                    t.stop()
                    self._thread = None
            raise
        fut = t.submit(lambda: fn(ctx))
        try:
            return fut.result(timeout=limit)
        except cf.TimeoutError:
            with self._lock:
                if self._thread is t:
                    self._stuck = True
            raise SolidWorksBusy(
                f"SolidWorks không trả lời sau {limit:.0f} s (có thể đang mở hộp thoại)."
            ) from None

    def close(self) -> None:
        with self._lock:
            if self._thread is not None:
                self._thread.stop()
                self._thread = None
