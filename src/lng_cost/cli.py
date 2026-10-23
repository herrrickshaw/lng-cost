"""Command-line interface: `lng-cost` or `python -m lng_cost.cli`."""
from __future__ import annotations

import argparse
import json
import sys

from dataclasses import replace

from .capex import CapexBuild, REGAS, REGIONS, with_region
from .model import LiquefactionInputs, RegasInputs, ShippingInputs, estimate, sensitivity


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lng-cost", description="Estimate delivered LNG cost (USD/MMBtu).")
    p.add_argument("--capacity-mtpa", type=float, help="Liquefaction nameplate, Mtpa")
    p.add_argument("--capex-per-tpa", type=float, help="Liquefaction capex, USD per tonne/yr")
    p.add_argument("--feed-gas-price", type=float, help="Feed gas price, USD/MMBtu")
    p.add_argument("--discount-rate", type=float, help="Applies to liquefaction and regas")
    p.add_argument("--distance-nm", type=float, help="One-way shipping distance, nautical miles")
    p.add_argument("--charter-rate", type=float, help="Vessel charter, USD/day")
    p.add_argument("--bunker-price", type=float, help="Fuel price, USD/tonne")
    p.add_argument("--regas-capex-per-tpa", type=float, help="Regas capex, USD per tonne/yr")
    p.add_argument("--bottom-up", action="store_true",
                   help="Build capex from steel, cement, labour and equipment instead of flat USD/tpa")
    p.add_argument("--region", choices=sorted(REGIONS), default="reference")
    p.add_argument("--steel-price", type=float, help="Fabricated steel, USD/t")
    p.add_argument("--cement-price", type=float, help="Cement, USD/t")
    p.add_argument("--labour-rate", type=float, help="Craft labour, USD/hour (overrides region)")
    p.add_argument("--equipment-index", type=float, help="Purchased-equipment cost index (1.0 = reference)")
    p.add_argument("--sensitivity", action="store_true", help="Print +/-20%% capex-driver sensitivity (implies --bottom-up)")
    p.add_argument("--json", action="store_true", help="Emit full JSON")
    return p


def main(argv: list[str] | None = None) -> int:
    a = _build_parser().parse_args(argv)
    liq, ship, rg = LiquefactionInputs(), ShippingInputs(), RegasInputs()
    if a.capacity_mtpa is not None:
        liq.capacity_mtpa = rg.capacity_mtpa = a.capacity_mtpa
    if a.capex_per_tpa is not None:
        liq.capex_per_tpa = a.capex_per_tpa
    if a.feed_gas_price is not None:
        liq.feed_gas_price = a.feed_gas_price
    if a.discount_rate is not None:
        liq.discount_rate = rg.discount_rate = a.discount_rate
    if a.distance_nm is not None:
        ship.distance_nm = a.distance_nm
    if a.charter_rate is not None:
        ship.charter_rate_per_day = a.charter_rate
    if a.bunker_price is not None:
        ship.bunker_price_per_t = a.bunker_price
    if a.regas_capex_per_tpa is not None:
        rg.capex_per_tpa = a.regas_capex_per_tpa

    lb = rb = None
    if a.bottom_up or a.sensitivity:
        lb = with_region(CapexBuild(capacity_mtpa=liq.capacity_mtpa), a.region)
        if a.labour_rate is not None:
            lb = replace(lb, region=replace(lb.region, labour_rate=a.labour_rate))
        pr = lb.prices
        if a.steel_price is not None:
            pr = replace(pr, steel_usd_per_t=a.steel_price)
        if a.cement_price is not None:
            pr = replace(pr, cement_usd_per_t=a.cement_price)
        if a.equipment_index is not None:
            pr = replace(pr, equipment_index=a.equipment_index)
        lb = replace(lb, prices=pr)
        rb = replace(with_region(CapexBuild(capacity_mtpa=rg.capacity_mtpa), a.region),
                     quantities=REGAS, prices=pr)

    e = estimate(liq, ship, rg, liq_build=lb, regas_build=rb)
    if a.json:
        json.dump(e.to_dict(), sys.stdout, indent=2)
        print()
        return 0
    rows = [
        ("Feed gas (incl. fuel & loss)", e.feed_gas),
        ("Liquefaction capital charge", e.liquefaction_capital),
        ("Liquefaction fixed O&M", e.liquefaction_opex),
        ("Liquefaction other variable", e.liquefaction_variable),
        ("FOB cost", e.fob_price),
        ("Shipping", e.shipping),
        ("Regasification", e.regas),
        ("DELIVERED cost", e.delivered),
    ]
    for name, val in rows:
        print(f"{name:<32}{val:>8.2f}  USD/MMBtu")
    print(f"\nRound trip: {e.voyage['round_trip_days']:.1f} days, "
          f"boil-off {e.voyage['boil_off_fraction']*100:.2f}%")
    bu = e.detail["bottom_up_capex"].get("liquefaction")
    if bu:
        print("\nLiquefaction capex build-up (USD million):")
        for k in ("steel", "cement", "concrete_other", "labour", "equipment", "indirects", "owners", "contingency", "total"):
            print(f"  {k:<16}{bu[k]/1e6:>10,.0f}")
        print(f"  => {bu['usd_per_tpa']:,.0f} USD per tonne/yr")
    if a.sensitivity:
        print("\nSensitivity of delivered cost to +/-20% (USD/MMBtu):")
        for k, (lo, hi) in sensitivity(lb, ship, rg, liq).items():
            print(f"  {k:<18}{lo:>+7.3f} / {hi:>+7.3f}")
    print("Defaults are illustrative placeholders; see README.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
