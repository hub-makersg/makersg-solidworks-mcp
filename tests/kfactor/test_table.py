import pytest

from swlamp.kfactor.table import CALIBRATED, PROVISIONAL, Entry, Key, KTable, KTableError


def test_unknown_key_returns_provisional_k_from_radius_ratio(tmp_path):
    table = KTable(tmp_path / "k.json")
    looked = table.lookup(Key("aluminium", 1.5))
    # aluminium, die 6T = 9 mm -> R ≈ 0.12 × 9 = 1.08, R/T = 0.72 < 1
    assert looked.status == PROVISIONAL
    assert looked.radius == pytest.approx(1.08)
    assert looked.k == pytest.approx(0.38)


def test_provisional_k_never_uses_solidworks_default(tmp_path):
    table = KTable(tmp_path / "k.json")
    for material in ("stainless", "steel", "aluminium"):
        for t in (0.5, 0.8, 1.0, 1.5, 2.0):
            assert table.lookup(Key(material, t)).k != 0.5


def test_calibrated_row_only_covers_90_degree_bends(tmp_path):
    table = KTable(tmp_path / "k.json")
    key = Key("stainless", 0.8)
    table.store(key, Entry(k=0.44, radius=1.0, status=CALIBRATED))
    looked = table.lookup(key)
    assert looked.status_for(90) == CALIBRATED
    assert looked.status_for(135) == PROVISIONAL
    assert looked.status_for(180) == PROVISIONAL


def test_keys_differ_by_shop_and_die(tmp_path):
    table = KTable(tmp_path / "k.json")
    table.store(Key("steel", 1.0, shop="a", die_v=8), Entry(k=0.41, radius=1.28, status=CALIBRATED))
    assert table.lookup(Key("steel", 1.0, shop="b", die_v=8)).status == PROVISIONAL
    assert table.lookup(Key("steel", 1.0, shop="a", die_v=10)).status == PROVISIONAL
    assert table.lookup(Key("steel", 1.0, shop="a", die_v=8)).k == pytest.approx(0.41)


def test_corrupt_table_reports_and_is_not_overwritten(tmp_path):
    path = tmp_path / "k.json"
    path.write_text("{not json", encoding="utf-8")
    table = KTable(path)
    with pytest.raises(KTableError, match="Bảng K bị hỏng"):
        table.lookup(Key("steel", 1.0))
    with pytest.raises(KTableError):
        table.store(Key("steel", 1.0), Entry(k=0.4, radius=1, status=CALIBRATED))
    assert path.read_text(encoding="utf-8") == "{not json"
