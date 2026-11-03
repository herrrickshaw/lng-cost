"""Smoke tests for the `lng-cost` CLI; text and JSON output pinned pre-refactor."""
from __future__ import annotations

import json

import pytest

from lng_cost.cli import main


def test_default_text_report(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "DELIVERED cost                      8.49  USD/MMBtu" in out
    assert "FOB cost                            6.87  USD/MMBtu" in out
    assert "Round trip: 27.5 days, boil-off 1.23%" in out
    assert "capex build-up" not in out
    assert out.rstrip().endswith("Defaults are illustrative placeholders; see README.")


def test_readme_flags(capsys):
    assert main(["--distance-nm", "9000", "--capex-per-tpa", "1000"]) == 0
    out = capsys.readouterr().out
    assert "DELIVERED cost                      9.55  USD/MMBtu" in out
    assert "Round trip: 47.1 days, boil-off 2.21%" in out


def test_json_output(capsys):
    assert main(["--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["delivered"] == pytest.approx(8.493033683611172)
    assert "vessels_for_mtpa_factor" not in d["voyage"]
    assert d["detail"]["bottom_up_capex"] == {}


def test_bottom_up_with_region_and_sensitivity(capsys):
    assert main(["--bottom-up", "--region", "australia", "--steel-price", "2400",
                 "--labour-rate", "90", "--sensitivity"]) == 0
    out = capsys.readouterr().out
    assert "DELIVERED cost                     10.06  USD/MMBtu" in out
    assert "  => 1,311 USD per tonne/yr" in out
    assert "  total                6,556" in out
    assert "  equipment_index    -0.448 /  +0.448" in out
    assert "  cement_usd_per_t   -0.001 /  +0.001" in out


def test_bottom_up_json_builds_regas_too(capsys):
    assert main(["--bottom-up", "--region", "us_gulf", "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["delivered"] == pytest.approx(8.879940173443062)
    assert d["regas"] == pytest.approx(0.7118927523035387)
    assert d["detail"]["bottom_up_capex"]["regas"]["usd_per_tpa"] == pytest.approx(169.5083257352941)


def test_capacity_and_discount_apply_to_both_plants(capsys):
    assert main(["--capacity-mtpa", "8", "--discount-rate", "0.08", "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["detail"]["liquefaction"]["capacity_mtpa"] == 8
    assert d["detail"]["regas"]["capacity_mtpa"] == 8
    assert d["detail"]["regas"]["discount_rate"] == 0.08


def test_unknown_region_rejected():
    with pytest.raises(SystemExit):
        main(["--region", "mars"])
