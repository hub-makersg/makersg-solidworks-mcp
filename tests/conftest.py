import pytest


@pytest.fixture(scope="session")
def sw_worker():
    """A worker attached to the user's running SolidWorks; skips when none is available."""
    from swlamp.sw.connection import SolidWorksNotRunning, attach, probe
    from swlamp.sw.worker import StaWorker

    worker = StaWorker(on_start=attach, probe=probe, timeout=300)
    try:
        worker.run(lambda sw: sw.revision(), timeout=60)
    except (SolidWorksNotRunning, ImportError) as exc:
        worker.close()
        pytest.skip(f"SolidWorks unavailable: {exc}")
    yield worker
    worker.close()
