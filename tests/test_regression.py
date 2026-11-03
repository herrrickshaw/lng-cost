"""Characterisation tests: numeric outputs pinned before the 2026-11 refactor.

Every value below was captured from the pre-refactor code (commit 8766e1b) on the
default and README scenarios. A failure here means behaviour changed.
"""
from __future__ import annotations

import pytest

from lng_cost import CapexBuild, Prices, ShippingInputs, build_capex, estimate, sensitivity, with_region
from lng_cost.model import voyage

REL = 1e-9


def test_default_scenario_delivered_cost():
    e = estimate()
    assert e.delivered == pytest.approx(8.493033683611172, rel=REL)
    assert e.fob_price == pytest.approx(6.870268860687524, rel=REL)
    assert e.shipping == pytest.approx(0.9812934087769376, rel=REL)
    assert e.regas == pytest.approx(0.6414714141467097, rel=REL)


def test_default_voyage():
    v = voyage(ShippingInputs())
    assert v["round_trip_days"] == pytest.approx(27.50980392156863, rel=REL)
    assert v["cargo_loaded_mmbtu"] == pytest.approx(4071600.0, rel=REL)
    assert v["delivered_mmbtu"] == pytest.approx(4021702.9411764704, rel=REL)
    assert v["boil_off_fraction"] == pytest.approx(0.012254901960784315, rel=REL)
    assert v["round_trip_cost_usd"] == pytest.approx(3946470.5882352944, rel=REL)
    assert v["usd_per_mmbtu_delivered"] == pytest.approx(0.9812934087769376, rel=REL)


def test_default_bottom_up_capex_components():
    b = build_capex(CapexBuild())
    expected = {
        "steel": 200_000_000.0,
        "cement": 5_460_000.0,
        "concrete_other": 18_000_000.0,
        "labour": 540_000_000.0,
        "equipment": 2_000_000_000.0,
        "direct": 2_763_460_000.0,
        "indirects": 690_865_000.0,
        "owners": 345_432_500.0,
        "contingency": 569_963_625.0,
        "total": 4_369_721_125.0,
        "usd_per_tpa": 873.944225,
        "concrete_usd_per_m3": 195.5,
    }
    assert set(b) == set(expected)
    for k, val in expected.items():
        assert b[k] == pytest.approx(val, rel=REL), k


def test_readme_bottom_up_scenario_and_sensitivity():
    b = with_region(CapexBuild(capacity_mtpa=5, prices=Prices(steel_usd_per_t=2400)), "us_gulf")
    e = estimate(liq_build=b)
    assert e.delivered == pytest.approx(8.84851056299051, rel=REL)
    assert e.detail["bottom_up_capex"]["liquefaction"]["usd_per_tpa"] == pytest.approx(1015.3265779411767, rel=REL)
    s = sensitivity(b)
    assert list(s) == ["equipment_index", "labour_rate", "steel_usd_per_t", "cement_usd_per_t"]
    assert s["equipment_index"] == pytest.approx((-0.40941314089492664, 0.4094131408949302), rel=1e-6)
    assert s["labour_rate"] == pytest.approx((-0.16514143498282863, 0.16514143498282863), rel=1e-6)
    assert s["steel_usd_per_t"] == pytest.approx((-0.04679007324513407, 0.046790073245135844), rel=1e-6)
    assert s["cement_usd_per_t"] == pytest.approx((-0.0010644741663270452, 0.0010644741663270452), rel=1e-6)
