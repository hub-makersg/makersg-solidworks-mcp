import contextlib
import io

import pytest

pytestmark = pytest.mark.sw


def test_attach_reports_solidworks_2025(sw_worker):
    assert sw_worker.run(lambda sw: sw.revision()).startswith("33.")


def test_quiet_sets_and_restores_toggles(sw_worker):
    def roundtrip(sw):
        key = sw.const.swSTLShowInfoOnSave
        before = sw.app.GetUserPreferenceToggle(key)
        sw.quiet()
        during = sw.app.GetUserPreferenceToggle(key)
        sw.restore()
        return before, during, sw.app.GetUserPreferenceToggle(key)

    before, during, after = sw_worker.run(roundtrip)
    assert during is False
    assert after == before


def test_typelib_generation_writes_nothing_to_stdout():
    from swlamp.sw.connection import ensure_typelibs

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ensure_typelibs()
    assert buf.getvalue() == ""
