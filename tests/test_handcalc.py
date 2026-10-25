"""Hand-calculated checks of the levelized LNG chain cost model.

Expected values below were worked out by hand from the textbook formulas
(CRF annuity, feed gross-up, round-trip voyage arithmetic), not taken from the
code's own output:

  CRF(10 %, 20 y) = 0.1 * 1.1^20 / (1.1^20 - 1)                 = 0.1174596
  Default liquefaction: capex 900 USD/tpa x 5 Mtpa             = 4.5e9 USD
    annual MMBtu = 5e6 t x 0.92 x 52                            = 2.392e8
    capital = 4.5e9 x 0.1174596 / 2.392e8                       = 2.20973
    fixed O&M = 0.03 x 4.5e9 / 2.392e8                          = 0.56438
    feed = 3.50 / (1 - 0.09)                                    = 3.84615
    FOB = 2.20973 + 0.56438 + 3.84615 + 0.25                    = 6.87027
  Default voyage (5000 nm, 17 kn):
    408 nm/day -> sea days 24.5098, round trip 27.5098
    cargo 174000 m3 x 0.45 = 78300 t, laden 12.2549 d, boil-off 1.22549 %
    delivered 78300 x 0.98774510 x 52 = 4,021,702.9 MMBtu
    cost 27.5098 x 90000 + 24.5098 x 100 x 600 = 3,946,470.6 USD
    -> 0.981293 USD/MMBtu delivered (freight only)
  Default regas: 150 x 5e6 x (CRF(10 %, 25 y)=0.1101681 + 0.04) / (5e6 x 0.8 x 52) + 0.10
                 = 0.641471
  Default bottom-up capex: direct = 2e8 + 5.46e6 + 1.8e7 + 5.4e8 + 2e9 = 2.76346e9
                 total = direct x 1.25 x 1.10 x 1.15 = 4.369721e9 -> 873.94 USD/tpa
"""
import pytest

from lng_cost import CapexBuild, LiquefactionInputs, RegasInputs, ShippingInputs, crf, estimate
from lng_cost.capex import build_capex, REGIONS
from lng_cost.model import liquefaction_cost, regas_cost, scale_capex, voyage
from lng_cost.cli import main


def test_crf_hand_values():
    assert crf(0.10, 20) == pytest.approx(0.1174596, rel=1e-6)
    assert crf(0.08, 25) == pytest.approx(0.0936788, rel=1e-5)
    # one-year annuity repays principal plus one year of interest
    assert crf(0.07, 1) == pytest.approx(1.07)


def test_crf_rejects_negative_years():
    with pytest.raises(ValueError):
        crf(0.1, -5)


def test_scale_capex_default_exponent_and_identity():
    assert scale_capex(1000, 5, 5) == pytest.approx(1000)
    # 2x capacity at exponent 0.65 -> 2^0.65 = 1.569168
    assert scale_capex(1000, 5, 10) == pytest.approx(1569.168, rel=1e-6)
    with pytest.raises(ValueError):
        scale_capex(1000, 0, 5)


def test_liquefaction_default_components_by_hand():
    l = liquefaction_cost(LiquefactionInputs())
    assert l["capex_usd"] == pytest.approx(4.5e9)
    assert l["capital"] == pytest.approx(2.209734, rel=1e-5)
    assert l["fixed_opex"] == pytest.approx(0.564381, rel=1e-5)
    assert l["feed_gas"] == pytest.approx(3.846154, rel=1e-6)
    assert l["fob"] == pytest.approx(6.870269, rel=1e-5)


def test_voyage_default_by_hand():
    v = voyage(ShippingInputs())
    assert v["round_trip_days"] == pytest.approx(27.509804, rel=1e-6)
    assert v["boil_off_fraction"] == pytest.approx(0.0122549, rel=1e-5)
    assert v["delivered_mmbtu"] == pytest.approx(4_021_702.94, rel=1e-6)
    assert v["round_trip_cost_usd"] == pytest.approx(3_946_470.59, rel=1e-6)
    assert v["usd_per_mmbtu_delivered"] == pytest.approx(0.981293, rel=1e-5)


def test_voyage_boiloff_is_capped_at_half_cargo():
    v = voyage(ShippingInputs(distance_nm=1_000_000))
    assert v["boil_off_fraction"] == 0.5


def test_canal_fee_adds_linearly():
    base = voyage(ShippingInputs())
    canal = voyage(ShippingInputs(canal_fees_per_round_trip=500_000))
    assert canal["usd_per_mmbtu_delivered"] - base["usd_per_mmbtu_delivered"] == pytest.approx(
        500_000 / base["delivered_mmbtu"])


def test_regas_default_by_hand():
    assert regas_cost(RegasInputs()) == pytest.approx(0.641471, rel=1e-5)


def test_bottom_up_default_by_hand():
    b = build_capex(CapexBuild())
    assert b["direct"] == pytest.approx(2.76346e9)
    assert b["total"] == pytest.approx(4.369721125e9)
    assert b["usd_per_tpa"] == pytest.approx(873.944, rel=1e-5)
    # concrete unit cost: 0.35 t/m3 x 130 + 150 = 195.5 USD/m3
    assert b["concrete_usd_per_m3"] == pytest.approx(195.5)


def test_bottom_up_scaling_matches_six_tenths_rule():
    # every quantity scales with (cap/5)^0.65, so total capex obeys the same rule
    t5 = build_capex(CapexBuild(capacity_mtpa=5))["total"]
    t10 = build_capex(CapexBuild(capacity_mtpa=10))["total"]
    assert t10 / t5 == pytest.approx(2 ** 0.65, rel=1e-9)


def test_lower_productivity_raises_labour_inversely():
    from dataclasses import replace
    base = CapexBuild()
    slow = replace(base, region=replace(base.region, productivity=0.5))
    assert build_capex(slow)["labour"] == pytest.approx(2 * build_capex(base)["labour"])


def test_bottom_up_rejects_zero_capacity():
    with pytest.raises(ValueError):
        build_capex(CapexBuild(capacity_mtpa=0))


def test_regions_are_all_buildable():
    for name in REGIONS:
        assert build_capex(CapexBuild(region=REGIONS[name]))["total"] > 0


def test_delivered_cost_charges_value_of_boiled_off_cargo():
    """Landed cost per delivered MMBtu = (FOB x loaded + freight) / delivered + regas.

    The buyer pays FOB on the loaded cargo but only receives (1 - boil-off) of it,
    and the model burns separate bunkers, so the boiled-off LNG is a pure loss.
    """
    e = estimate()
    v = e.voyage
    loaded, delivered = v["cargo_loaded_mmbtu"], v["delivered_mmbtu"]
    landed = (e.fob_price * loaded + v["round_trip_cost_usd"]) / delivered
    assert e.delivered == pytest.approx(landed + e.regas, rel=1e-9)
    # by hand for defaults: 6.870269/(1-0.0122549) + 0.981293 + 0.641471
    assert e.delivered == pytest.approx(6.955507 + 0.981293 + 0.641471, rel=1e-5)


def test_zero_distance_delivered_has_no_boiloff_charge():
    e = estimate(ship=ShippingInputs(distance_nm=0))
    assert e.delivered == pytest.approx(e.fob_price + e.shipping + e.regas)
    # 3 port days of charter only, over the full cargo
    assert e.shipping == pytest.approx(3 * 90000 / (78300 * 52), rel=1e-9)


def test_cli_text_and_json(capsys):
    assert main(["--distance-nm", "9000"]) == 0
    out = capsys.readouterr().out
    assert "DELIVERED cost" in out
    import json
    assert main(["--json", "--bottom-up", "--region", "australia"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["detail"]["bottom_up_capex"]["liquefaction"]["total"] > 0
