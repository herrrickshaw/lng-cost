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
