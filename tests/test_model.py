import math
import pytest
from lng_cost import (LiquefactionInputs, ShippingInputs, RegasInputs, crf, estimate)
from lng_cost.model import scale_capex, liquefaction_cost, voyage


def test_crf_known_value():
    assert crf(0.10, 20) == pytest.approx(0.117459, rel=1e-4)


def test_crf_zero_rate():
    assert crf(0, 10) == pytest.approx(0.1)


def test_scale_capex_sixtenths():
    assert scale_capex(100, 1, 2, 0.6) == pytest.approx(100 * 2 ** 0.6)


def test_delivered_is_sum_of_parts():
    e = estimate()
    assert e.delivered == pytest.approx(e.fob_price + e.shipping + e.regas)
    assert e.fob_price == pytest.approx(
        e.feed_gas + e.liquefaction_capital + e.liquefaction_opex + e.liquefaction_variable)


def test_feed_gas_grossed_up_for_fuel():
    l = liquefaction_cost(LiquefactionInputs(feed_gas_price=3.0, fuel_and_loss=0.10))
    assert l["feed_gas"] == pytest.approx(3.0 / 0.9)


def test_higher_capex_raises_cost():
    lo = estimate(LiquefactionInputs(capex_per_tpa=600)).delivered
    hi = estimate(LiquefactionInputs(capex_per_tpa=1200)).delivered
    assert hi > lo


def test_shipping_increases_with_distance():
    near = voyage(ShippingInputs(distance_nm=2000))["usd_per_mmbtu_delivered"]
    far = voyage(ShippingInputs(distance_nm=10000))["usd_per_mmbtu_delivered"]
    assert far > near


def test_zero_distance_has_no_boiloff():
    v = voyage(ShippingInputs(distance_nm=0))
    assert v["boil_off_fraction"] == 0


def test_bad_inputs():
    with pytest.raises(ValueError):
        crf(0.1, 0)


def test_bottom_up_components_sum_and_replace_flat_capex():
    from lng_cost import CapexBuild, build_capex
    b = build_capex(CapexBuild())
    parts = b["steel"] + b["cement"] + b["concrete_other"] + b["labour"] + b["equipment"]
    assert b["direct"] == pytest.approx(parts)
    assert b["total"] == pytest.approx(b["direct"] * 1.25 * 1.10 * 1.15)
    e = estimate(liq_build=CapexBuild())
    assert e.liquefaction_capex_usd == pytest.approx(b["total"])


def test_input_prices_raise_capex():
    from dataclasses import replace
    from lng_cost import CapexBuild, build_capex
    base = CapexBuild()
    for kw in ({"steel_usd_per_t": 4000}, {"cement_usd_per_t": 400}, {"equipment_index": 1.5}):
        hi = build_capex(replace(base, prices=replace(base.prices, **kw)))
        assert hi["total"] > build_capex(base)["total"]
    hi = build_capex(replace(base, region=replace(base.region, labour_rate=90)))
    assert hi["labour"] == pytest.approx(2 * build_capex(base)["labour"])


def test_scale_economies_lower_unit_cost():
    from dataclasses import replace
    from lng_cost import CapexBuild, build_capex
    small = build_capex(CapexBuild(capacity_mtpa=2))["usd_per_tpa"]
    large = build_capex(CapexBuild(capacity_mtpa=10))["usd_per_tpa"]
    assert large < small


def test_regions_and_sensitivity():
    from lng_cost import CapexBuild, with_region, sensitivity, build_capex
    assert build_capex(with_region(CapexBuild(), "australia"))["total"] > build_capex(CapexBuild())["total"]
    with pytest.raises(ValueError):
        with_region(CapexBuild(), "mars")
    sens = sensitivity(CapexBuild())
    assert set(sens) == {"steel_usd_per_t", "cement_usd_per_t", "labour_rate", "equipment_index"}
    assert all(lo < 0 < hi for lo, hi in sens.values())
    # equipment dominates by construction of the default quantities
    assert next(iter(sens)) == "equipment_index"
