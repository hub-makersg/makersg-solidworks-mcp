import pytest

from swlamp.sw import equations


def test_non_order_variable_is_refused_before_opening_solidworks():
    with pytest.raises(equations.EquationError, match="ord_"):
        equations.check_names({"Width": 3, "ord_width": 4})
