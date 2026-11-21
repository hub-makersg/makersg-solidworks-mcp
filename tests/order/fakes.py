"""Shared helpers for faking the SolidWorks side of an order."""


def hits_for(blank, shift=0.0):
    """Where SolidWorks would report each checkpoint ray landing, moved by ``shift`` mm."""
    out = []
    for cp in blank.checks:
        point = list(cp.origin)
        point[cp.axis] = cp.value + shift
        out.append(tuple(point))
    return out
