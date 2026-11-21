import threading
import time

import pytest

from swlamp.sw.worker import SolidWorksBusy, StaWorker


def test_job_runs_on_worker_thread_and_returns_result():
    w = StaWorker(on_start=lambda: "ctx")
    caller = threading.get_ident()
    result = w.run(lambda ctx: (ctx, threading.get_ident()))
    assert result[0] == "ctx"
    assert result[1] != caller
    assert w.run(lambda ctx: threading.get_ident()) == result[1]
    w.close()


def test_job_exception_propagates():
    w = StaWorker()
    with pytest.raises(ValueError, match="boom"):
        w.run(lambda ctx: (_ for _ in ()).throw(ValueError("boom")))
    assert w.run(lambda ctx: 1) == 1
    w.close()


def test_hung_job_times_out_and_next_job_fails_fast():
    never = threading.Event()
    w = StaWorker(probe=lambda: never.wait(), timeout=0.3, probe_timeout=0.2)
    with pytest.raises(SolidWorksBusy):
        w.run(lambda ctx: never.wait())
    start = time.monotonic()
    with pytest.raises(SolidWorksBusy, match="đang bận"):
        w.run(lambda ctx: 1, timeout=10)
    assert time.monotonic() - start < 2.0


def test_worker_restarts_after_probe_succeeds():
    never = threading.Event()
    probe_ok = threading.Event()
    w = StaWorker(probe=lambda: probe_ok.is_set() or never.wait(), timeout=0.3, probe_timeout=0.2)
    with pytest.raises(SolidWorksBusy):
        w.run(lambda ctx: never.wait())
    probe_ok.set()
    assert w.run(lambda ctx: "fresh", timeout=5) == "fresh"
    w.close()


def test_on_start_failure_reaches_caller():
    def boom():
        raise RuntimeError("no solidworks")

    w = StaWorker(on_start=boom)
    with pytest.raises(RuntimeError, match="no solidworks"):
        w.run(lambda ctx: 1)


def test_worker_retries_attach_after_solidworks_is_started():
    attempts = []

    def attach():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("SolidWorks chưa chạy")
        return "sw"

    w = StaWorker(on_start=attach)
    with pytest.raises(RuntimeError, match="chưa chạy"):
        w.run(lambda ctx: ctx)
    assert w.run(lambda ctx: ctx) == "sw"
    w.close()
