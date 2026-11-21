from unittest import mock

import pytest
import pywintypes

from swlamp.sw import connection


def test_attach_without_running_solidworks_says_so():
    err = pywintypes.com_error(connection.MK_E_UNAVAILABLE, "Operation unavailable", None, None)
    with mock.patch("pythoncom.GetActiveObject", side_effect=err):
        with pytest.raises(connection.SolidWorksNotRunning, match="SolidWorks chưa chạy"):
            connection.attach()
