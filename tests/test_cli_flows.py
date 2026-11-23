"""lng-cost CLI: every override flag reaches the model, JSON and text output, bottom-up and sensitivity modes."""
import json

import pytest

from lng_cost import cli
from lng_cost.capex import CapexBuild, REGAS, with_region
from lng_cost.model import LiquefactionInputs, RegasInputs, ShippingInputs, estimate


def run(argv, capsys):
    rc = cli.main(argv)
    return rc, capsys.readouterr().out


def js(argv, capsys):
    rc, out = run(argv + ["--json"], capsys)
    assert rc == 0
    return json.loads(out)


def test_defaults_text_report(capsys):
    rc, out = run([], capsys)
    e = estimate()
    assert rc == 0
    assert f"{'DELIVERED cost':<32}{e.delivered:>8.2f}  USD/MMBtu" in out
    for label in ("Feed gas (incl. fuel & loss)", "Liquefaction capital charge", "Liquefaction fixed O&M",
                  "Liquefaction other variable", "FOB cost", "Shipping", "Regasification"):
        assert label in out
    assert f"Round trip: {e.voyage['round_trip_days']:.1f} days, boil-off {e.voyage['boil_off_fraction'] * 100:.2f}%" in out
    assert "capex build-up" not in out and out.rstrip().endswith("Defaults are illustrative placeholders; see README.")


def test_json_matches_library_estimate(capsys):
    assert js([], capsys) == json.loads(json.dumps(estimate().to_dict()))


def test_each_override_changes_the_model_input(capsys):
    d = js(["--capacity-mtpa", "3", "--capex-per-tpa", "1000", "--feed-gas-price", "5", "--discount-rate", "0.07",
            "--distance-nm", "8000", "--charter-rate", "50000", "--bunker-price", "400",
            "--regas-capex-per-tpa", "200"], capsys)["detail"]
    liq, ship, rg = d["liquefaction"], d["shipping"], d["regas"]
    assert liq["capacity_mtpa"] == 3 and rg["capacity_mtpa"] == 3          # capacity applies to both plants
    assert liq["capex_per_tpa"] == 1000 and liq["feed_gas_price"] == 5
    assert liq["discount_rate"] == 0.07 and rg["discount_rate"] == 0.07    # discount rate applies to both
    assert ship["distance_nm"] == 8000 and ship["charter_rate_per_day"] == 50000
    assert ship["bunker_price_per_t"] == 400 and rg["capex_per_tpa"] == 200


def test_zero_valued_override_is_applied_not_ignored(capsys):
    d = js(["--feed-gas-price", "0", "--discount-rate", "0", "--bunker-price", "0"], capsys)["detail"]
    assert d["liquefaction"]["feed_gas_price"] == 0 and d["liquefaction"]["discount_rate"] == 0
    assert d["shipping"]["bunker_price_per_t"] == 0


def test_overrides_match_direct_library_call(capsys):
    got = js(["--capacity-mtpa", "2", "--distance-nm", "9000"], capsys)
    liq = LiquefactionInputs(capacity_mtpa=2.0)
    rg = RegasInputs(capacity_mtpa=2.0)
    want = estimate(liq, ShippingInputs(distance_nm=9000.0), rg)
    assert got["delivered"] == pytest.approx(want.delivered)


def test_bottom_up_text_report_has_capex_buildup(capsys):
    rc, out = run(["--bottom-up", "--region", "us_gulf"], capsys)
    assert rc == 0 and "Liquefaction capex build-up (USD million):" in out
    for k in ("steel", "cement", "concrete_other", "labour", "equipment", "indirects", "owners", "contingency",
              "total"):
        assert f"  {k:<16}" in out
    assert "USD per tonne/yr" in out and "Sensitivity" not in out


def test_bottom_up_matches_library_for_region_and_price_overrides(capsys):
    d = js(["--bottom-up", "--region", "middle_east", "--steel-price", "1500", "--cement-price", "100",
            "--labour-rate", "30", "--equipment-index", "1.2"], capsys)
    from dataclasses import replace
    lb = with_region(CapexBuild(), "middle_east")
    lb = replace(lb, region=replace(lb.region, labour_rate=30.0))
    pr = replace(lb.prices, steel_usd_per_t=1500.0, cement_usd_per_t=100.0, equipment_index=1.2)
    lb = replace(lb, prices=pr)
    rb = replace(with_region(CapexBuild(), "middle_east"), quantities=REGAS, prices=pr)
    want = estimate(liq_build=lb, regas_build=rb)
    assert d["delivered"] == pytest.approx(want.delivered)
    assert d["detail"]["bottom_up_capex"]["regas"]["total"] == pytest.approx(want.detail["bottom_up_capex"]["regas"]["total"])


def test_capacity_flows_into_bottom_up_build(capsys):
    a = js(["--bottom-up", "--capacity-mtpa", "2"], capsys)["detail"]["bottom_up_capex"]
    b = js(["--bottom-up"], capsys)["detail"]["bottom_up_capex"]
    assert a["liquefaction"]["total"] < b["liquefaction"]["total"]
    assert a["liquefaction"]["usd_per_tpa"] > b["liquefaction"]["usd_per_tpa"]       # diseconomy of small scale


def test_sensitivity_implies_bottom_up_and_prints_drivers(capsys):
    rc, out = run(["--sensitivity"], capsys)
    assert rc == 0 and "capex build-up" in out
    assert "Sensitivity of delivered cost to +/-20% (USD/MMBtu):" in out
    lines = [ln for ln in out.splitlines() if " / " in ln]
    assert [ln.split()[0] for ln in lines].count("steel_usd_per_t") == 1 and len(lines) == 4
    swings = [abs(float(ln.split("/")[1]) - float(ln.split("/")[0].split()[-1])) for ln in lines]
    assert swings == sorted(swings, reverse=True)                             # sorted by swing, largest first


def test_unknown_region_and_bad_flags_exit(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--region", "mars"])
    with pytest.raises(SystemExit):
        cli.main(["--capacity-mtpa", "abc"])


def test_zero_capacity_bottom_up_raises_value_error():
    with pytest.raises(ValueError, match="capacity_mtpa must be > 0"):
        cli.main(["--bottom-up", "--capacity-mtpa", "0"])


# ------------------------------- mutation-driven additions -------------------------------

def test_liq_build_capacity_replaces_the_flat_input_capacity():
    e = estimate(LiquefactionInputs(capacity_mtpa=5.0), liq_build=CapexBuild(capacity_mtpa=2.0))
    assert e.detail["liquefaction"]["capacity_mtpa"] == 2.0
    assert e.liquefaction_capex_usd == pytest.approx(e.detail["bottom_up_capex"]["liquefaction"]["total"])


def test_sensitivity_default_swing_is_twenty_percent():
    from dataclasses import replace

    from lng_cost.model import sensitivity
    b = CapexBuild()
    default = sensitivity(b)
    explicit = sensitivity(b, delta=0.20)
    assert default == explicit and default != sensitivity(b, delta=0.10)
    lo, hi = default["steel_usd_per_t"]
    base = estimate(liq_build=b).delivered
    steel = replace(b.prices, steel_usd_per_t=b.prices.steel_usd_per_t * 0.8)
    assert lo == pytest.approx(estimate(liq_build=replace(b, prices=steel)).delivered - base)
    assert lo < 0 < hi


def test_material_factor_applies_to_cement_steel_and_other_concrete():
    from dataclasses import replace

    from lng_cost.capex import Region, build_capex
    ref = build_capex(CapexBuild())
    up = build_capex(replace(CapexBuild(), region=Region(material_factor=1.25)))
    for k in ("steel", "cement", "concrete_other"):
        assert up[k] == pytest.approx(ref[k] * 1.25), k
    assert up["labour"] == pytest.approx(ref["labour"]) and up["equipment"] == pytest.approx(ref["equipment"])
