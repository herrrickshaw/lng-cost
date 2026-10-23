"""Levelized LNG chain cost model.

All defaults are ILLUSTRATIVE placeholders in the range commonly quoted for
greenfield projects. They are not sourced benchmarks: replace them with
project- or quote-specific values before relying on any output.

Units: money in USD (real, constant), energy in MMBtu, mass in tonnes.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

MMBTU_PER_TONNE = 52.0  # typical LNG HHV, ~51-54 depending on composition
HOURS_PER_DAY = 24.0
KNOT_KM_PER_H = 1.852
M3_LNG_PER_TONNE = 1 / 0.45  # LNG density ~0.45 t/m3


def crf(rate: float, years: int) -> float:
    """Capital recovery factor: annuity share of capex per year."""
    if years <= 0:
        raise ValueError("years must be > 0")
    if rate == 0:
        return 1.0 / years
    return rate * (1 + rate) ** years / ((1 + rate) ** years - 1)


def scale_capex(base_capex: float, base_size: float, size: float, exponent: float = 0.65) -> float:
    """Capacity-scaling ('six-tenths') rule. Useful to rescale a reference plant."""
    if base_size <= 0 or size <= 0:
        raise ValueError("sizes must be > 0")
    return base_capex * (size / base_size) ** exponent


@dataclass
class LiquefactionInputs:
    capacity_mtpa: float = 5.0            # nameplate, million tonnes per year
    capex_per_tpa: float = 900.0          # USD per tonne/yr of nameplate capacity (EPC+owner's, excl. financing)
    utilisation: float = 0.92             # fraction of nameplate actually produced
    fixed_opex_pct_capex: float = 0.03    # annual fixed O&M as share of capex
    feed_gas_price: float = 3.50          # USD/MMBtu delivered to plant inlet
    fuel_and_loss: float = 0.09           # share of feed gas burned/lost (feed = LNG / (1 - this))
    other_variable: float = 0.25          # USD/MMBtu LNG (power, chemicals, etc.)
    discount_rate: float = 0.10
    life_years: int = 20


@dataclass
class ShippingInputs:
    distance_nm: float = 5000.0           # one-way nautical miles
    vessel_capacity_m3: float = 174000.0
    speed_knots: float = 17.0
    charter_rate_per_day: float = 90000.0  # USD/day time-charter equivalent
    bunker_burn_t_per_day: float = 100.0   # laden/ballast average fuel burn
    bunker_price_per_t: float = 600.0
    port_days_per_round_trip: float = 3.0
    boil_off_pct_per_day: float = 0.10     # % of cargo per day (laden leg)
    canal_fees_per_round_trip: float = 0.0


@dataclass
class RegasInputs:
    capex_per_tpa: float = 150.0          # USD per tonne/yr send-out capacity
    capacity_mtpa: float = 5.0
    utilisation: float = 0.80
    fixed_opex_pct_capex: float = 0.04
    variable: float = 0.10                # USD/MMBtu
    discount_rate: float = 0.10
    life_years: int = 25


@dataclass
class Estimate:
    feed_gas: float
    liquefaction_capex_usd: float
    liquefaction_capital: float
    liquefaction_opex: float
    liquefaction_variable: float
    fob_price: float
    shipping: float
    regas: float
    delivered: float
    voyage: dict
    detail: dict

    def to_dict(self) -> dict:
        return asdict(self)


def liquefaction_cost(q: LiquefactionInputs) -> dict:
    """Return per-MMBtu components of the FOB cost, USD/MMBtu LNG."""
    annual_t = q.capacity_mtpa * 1e6 * q.utilisation
    annual_mmbtu = annual_t * MMBTU_PER_TONNE
    capex = q.capex_per_tpa * q.capacity_mtpa * 1e6
    capital = capex * crf(q.discount_rate, q.life_years) / annual_mmbtu
    opex = capex * q.fixed_opex_pct_capex / annual_mmbtu
    feed = q.feed_gas_price / (1 - q.fuel_and_loss)
    return {
        "capex_usd": capex,
        "capital": capital,
        "fixed_opex": opex,
        "feed_gas": feed,
        "other_variable": q.other_variable,
        "fob": capital + opex + feed + q.other_variable,
    }


def voyage(s: ShippingInputs) -> dict:
    """Round-trip economics for one vessel; cost per MMBtu delivered."""
    speed_nm_day = s.speed_knots * HOURS_PER_DAY
    sea_days = 2 * s.distance_nm / speed_nm_day
    days = sea_days + s.port_days_per_round_trip
    cargo_t = s.vessel_capacity_m3 / M3_LNG_PER_TONNE
    laden_days = s.distance_nm / speed_nm_day
    boil_off = min(0.5, s.boil_off_pct_per_day / 100 * laden_days)
    delivered_t = cargo_t * (1 - boil_off)
    delivered_mmbtu = delivered_t * MMBTU_PER_TONNE
    cost = (
        days * s.charter_rate_per_day
        + sea_days * s.bunker_burn_t_per_day * s.bunker_price_per_t
        + s.canal_fees_per_round_trip
    )
    return {
        "round_trip_days": days,
        "cargo_loaded_mmbtu": cargo_t * MMBTU_PER_TONNE,
        "delivered_mmbtu": delivered_mmbtu,
        "boil_off_fraction": boil_off,
        "round_trip_cost_usd": cost,
        "usd_per_mmbtu_delivered": cost / delivered_mmbtu,
        "vessels_for_mtpa_factor": None,
    }


def regas_cost(r: RegasInputs) -> float:
    annual_mmbtu = r.capacity_mtpa * 1e6 * r.utilisation * MMBTU_PER_TONNE
    capex = r.capex_per_tpa * r.capacity_mtpa * 1e6
    return (
        capex * (crf(r.discount_rate, r.life_years) + r.fixed_opex_pct_capex) / annual_mmbtu
        + r.variable
    )


def estimate(
    liq: LiquefactionInputs | None = None,
    ship: ShippingInputs | None = None,
    regas: RegasInputs | None = None,
) -> Estimate:
    liq, ship, regas = liq or LiquefactionInputs(), ship or ShippingInputs(), regas or RegasInputs()
    l = liquefaction_cost(liq)
    v = voyage(ship)
    # shipping cost is per MMBtu delivered; per MMBtu loaded it is the same
    # numerator over a larger base, so boil-off is already charged to the buyer's side.
    shipping = v["usd_per_mmbtu_delivered"]
    rg = regas_cost(regas)
    # Regas send-out is per MMBtu received, so delivered cost needs no further adjustment.
    delivered = l["fob"] + shipping + rg
    v = {k: x for k, x in v.items() if x is not None}
    return Estimate(
        feed_gas=l["feed_gas"],
        liquefaction_capex_usd=l["capex_usd"],
        liquefaction_capital=l["capital"],
        liquefaction_opex=l["fixed_opex"],
        liquefaction_variable=l["other_variable"],
        fob_price=l["fob"],
        shipping=shipping,
        regas=rg,
        delivered=delivered,
        voyage=v,
        detail={
            "liquefaction": asdict(liq),
            "shipping": asdict(ship),
            "regas": asdict(regas),
        },
    )
