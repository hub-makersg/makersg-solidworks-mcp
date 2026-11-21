import hashlib

import pytest

from swlamp.sw import builder, equations

pytestmark = pytest.mark.sw
MM = 0.001


def make_param_part(sw, path, link_file=None):
    """A 20 × 10 mm plate whose width follows the global variable ord_width."""
    sw.app.SetUserPreferenceToggle(sw.const.swInputDimValOnCreate, False)
    raw = sw.app.NewDocument(
        sw.app.GetUserPreferenceStringValue(sw.const.swDefaultTemplatePart), 0, 0, 0
    )
    d = builder._Doc(sw, raw)
    d.begin_sketch(None)
    segs = d.sk.CreateCenterRectangle(0, 0, 0, 10 * MM, 5 * MM, 0)
    bottom = next(
        s
        for s in (sw.typed(x, "ISketchSegment") for x in segs)
        if abs(
            sw.typed(s, "ISketchLine").GetStartPoint2().Y
            - sw.typed(s, "ISketchLine").GetEndPoint2().Y
        )
        < 1e-9
    )
    d.doc.ClearSelection2(True)
    bottom.Select4(False, None)
    dim = d.doc.AddDimension2(0, -10 * MM, 0)
    # FullName is "D1@Sketch1@<document>"; an equation must name "D1@Sketch1".
    dim_name = sw.typed(dim, "IDisplayDimension").GetDimension2(0).FullName.rsplit("@", 1)[0]
    sketch = d.end_sketch()
    d.doc.ClearSelection2(True)
    sketch.Select2(False, 0)
    fd = sw.typed(d.fm.CreateDefinition(sw.const.swFmBaseFlange), "IBaseFlangeFeatureData")
    fd.Initialize(False, True, d.allowance(0.42), False, 0, True, 0.5, 0.0, 0.0)
    fd.UseGaugeTable = False
    fd.Thickness = 2 * MM
    fd.BendRadius = 1 * MM
    assert d.fm.CreateFeature(fd) is not None
    eqm = sw.typed(d.doc.GetEquationMgr(), "IEquationMgr")
    eqm.Add2(-1, '"ord_width" = 20', True)
    eqm.Add2(-1, f'"{dim_name}" = "ord_width"', True)
    if link_file is not None:
        link_file.write_text('"ord_width" = 20\n', encoding="utf-8")
        eqm.FilePath = str(link_file)
        eqm.LinkToFile = True
    d.doc.ForceRebuild3(False)
    ok, err, _ = d.ext.SaveAs3(str(path), 0, sw.const.swSaveAsOptions_Silent, None, None, 0, 0)
    assert ok, err
    return d.doc


def width_of(sw, doc):
    bbox, _ = builder.body_bbox(sw, doc)
    return bbox[3] - bbox[0]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_copy_gets_new_width_while_original_stays_untouched(sw_worker, tmp_path):
    src = tmp_path / "clip.SLDPRT"
    dest = tmp_path / "order" / "clip__o1.SLDPRT"

    def job(sw):
        original = make_param_part(sw, src)
        before = digest(src)
        # The user still has the original open while the order runs.
        copy = equations.open_copy(sw, src, dest)
        try:
            errors = equations.apply(sw, copy, {"ord_width": 30})
            result = (errors, width_of(sw, copy), equations.value_of(sw, original, "ord_width"))
        finally:
            builder.close(sw, copy.GetTitle())
            builder.close(sw, original.GetTitle())
        return result, before

    (errors, width, original_value), before = sw_worker.run(job)
    assert errors == []
    assert width == pytest.approx(30, abs=0.01)
    assert original_value == pytest.approx(20)
    assert digest(src) == before


def test_missing_variable_is_reported_and_nothing_exported(sw_worker, tmp_path):
    src = tmp_path / "clip2.SLDPRT"

    def job(sw):
        builder.close(sw, make_param_part(sw, src).GetTitle())
        copy = equations.open_copy(sw, src, tmp_path / "o" / "clip2__o2.SLDPRT")
        try:
            with pytest.raises(equations.EquationError, match="ord_depth"):
                equations.apply(sw, copy, {"ord_depth": 5})
        finally:
            builder.close(sw, copy.GetTitle())

    sw_worker.run(job)
    assert not list((tmp_path / "o").glob("*.3mf"))


def test_linked_external_equations_are_refused(sw_worker, tmp_path):
    src = tmp_path / "clip3.SLDPRT"
    link = tmp_path / "shared.txt"

    def job(sw):
        builder.close(sw, make_param_part(sw, src, link_file=link).GetTitle())
        copy = equations.open_copy(sw, src, tmp_path / "o3" / "clip3__o3.SLDPRT")
        try:
            with pytest.raises(equations.EquationError, match="liên kết file ngoài"):
                equations.apply(sw, copy, {"ord_width": 40})
        finally:
            builder.close(sw, copy.GetTitle())

    sw_worker.run(job)
    assert "40" not in link.read_text(encoding="utf-8")
