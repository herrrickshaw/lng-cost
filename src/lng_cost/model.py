"""Levelized LNG chain cost model.

All defaults are ILLUSTRATIVE placeholders in the range commonly quoted for
greenfield projects. They are not sourced benchmarks: replace them with
project- or quote-specific values before relying on any output.

Units: money in USD (real, constant), energy in MMBtu, mass in tonnes.
Every function here is pure: inputs in, numbers out, no I/O.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Callable

from .capex import CapexBuild, build_capex

MMBTU_PER_TONNE = 52.0  # typical LNG HHV, ~51-54 depending on composition
HOURS_PER_DAY = 24.0
KNOT_KM_PER_H = 1.852
M3_LNG_PER_TONNE = 1 / 0.45  # LNG density ~0.45 t/m3
TONNES_PER_MTPA = 1e6  # million tonnes per year -> tonnes per year
MAX_BOIL_OFF_FRACTION = 0.5  # cap on laden-leg boil-off so a long voyage never "delivers" nothing
PERCENT = 100.0


def crf(rate: float, years: int) -> float:
    """Capital recovery factor: annuity share of capex per year (fraction/yr).

    `rate` is the real discount rate as a fraction, `years` the economic life.
    """
    if years <= 0:
        raise ValueError("years must be > 0")
    if rate == 0:
        return 1.0 / years
    return rate * (1 + rate) ** years / ((1 + rate) ** years - 1)


def scale_capex(base_capex: float, base_size: float, size: float, exponent: float = 0.65) -> float:
    """Capacity-scaling ('six-tenths') rule: capex of `size` given a reference plant.

    `base_capex` and the result share a currency; `base_size`/`size` share a unit.
    """
    if base_size <= 0 or size <= 0:
        raise ValueError("sizes must be > 0")
    return base_capex * (size / base_size) ** exponent


@dataclass
class LiquefactionInputs:
    """Liquefaction plant parameters (flat USD/tpa capex route)."""

    capacity_mtpa: float = 5.0            # nameplate, million tonnes per year
    capex_per_tpa: float = 900.0          # USD per tonne/yr of nameplate capacity (EPC+owner's, excl. financing)
    utilisation: float = 0.92             # fraction of nameplate actually produced
    fixed_opex_pct_capex: float = 0.03    # annual fixed O&M as share of capex
    feed_gas_price: float = 3.50          # USD/MMBtu delivered to plant inlet
    fuel_and_loss: float = 0.09           # share of feed gas burned/lost (feed = LNG / (1 - this))
    other_variable: float = 0.25          # USD/MMBtu LNG (power, chemicals, etc.)
    discount_rate: float = 0.10           # real, fraction/yr
    life_years: int = 20


@dataclass
class ShippingInputs:
    """Single-vessel round-trip voyage parameters."""

    distance_nm: float = 5000.0           # one-way nautical miles
    vessel_capacity_m3: float = 174000.0
    speed_knots: float = 17.0
    charter_rate_per_day: float = 90000.0  # USD/day time-charter equivalent
    bunker_burn_t_per_day: float = 100.0   # laden/ballast average fuel burn
    bunker_price_per_t: float = 600.0
    port_days_per_round_trip: float = 3.0
    boil_off_pct_per_day: float = 0.10     # % of cargo per day (laden leg)
    canal_fees_per_round_trip: float = 0.0  # USD


@dataclass
class RegasInputs:
    """Regasification terminal parameters (levelized terminal charge)."""

    capex_per_tpa: float = 150.0          # USD per tonne/yr send-out capacity
    capacity_mtpa: float = 5.0
    utilisation: float = 0.80
    fixed_opex_pct_capex: float = 0.04
    variable: float = 0.10                # USD/MMBtu
    discount_rate: float = 0.10           # real, fraction/yr
    life_years: int = 25


@dataclass
class Estimate:
    """Delivered-cost breakdown; every money field is USD/MMBtu except `liquefaction_capex_usd`."""

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
    """Return per-MMBtu components of the FOB cost, USD/MMBtu LNG (plus `capex_usd`)."""
    annual_t = q.capacity_mtpa * TONNES_PER_MTPA * q.utilisation
    annual_mmbtu = annual_t * MMBTU_PER_TONNE
    capex = q.capex_per_tpa * q.capacity_mtpa * TONNES_PER_MTPA
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
    """Round-trip economics for one vessel; cost per MMBtu delivered (USD/MMBtu)."""
    speed_nm_day = s.speed_knots * HOURS_PER_DAY
    sea_days = 2 * s.distance_nm / speed_nm_day
    days = sea_days + s.port_days_per_round_trip
    cargo_t = s.vessel_capacity_m3 / M3_LNG_PER_TONNE
    laden_days = s.distance_nm / speed_nm_day
    boil_off = min(MAX_BOIL_OFF_FRACTION, s.boil_off_pct_per_day / PERCENT * laden_days)
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
    }


def regas_cost(r: RegasInputs) -> float:
    """Levelized regasification charge, USD/MMBtu sent out."""
    annual_mmbtu = r.capacity_mtpa * TONNES_PER_MTPA * r.utilisation * MMBTU_PER_TONNE
    capex = r.capex_per_tpa * r.capacity_mtpa * TONNES_PER_MTPA
    return (
        capex * (crf(r.discount_rate, r.life_years) + r.fixed_opex_pct_capex) / annual_mmbtu
        + r.variable
    )


def estimate(
    liq: LiquefactionInputs | None = None,
    ship: ShippingInputs | None = None,
    regas: RegasInputs | None = None,
    liq_build: CapexBuild | None = None,
    regas_build: CapexBuild | None = None,
) -> Estimate:
    """Delivered cost, USD/MMBtu. If a CapexBuild is given, its bottom-up USD/tpa replaces
    the corresponding flat capex_per_tpa (and its capacity replaces capacity_mtpa)."""
    liq, ship, regas = liq or LiquefactionInputs(), ship or ShippingInputs(), regas or RegasInputs()
    bu: dict = {}
    if liq_build is not None:
        bu["liquefaction"] = build_capex(liq_build)
        liq = replace(liq, capex_per_tpa=bu["liquefaction"]["usd_per_tpa"],
                      capacity_mtpa=liq_build.capacity_mtpa)
    if regas_build is not None:
        bu["regas"] = build_capex(regas_build)
        regas = replace(regas, capex_per_tpa=bu["regas"]["usd_per_tpa"],
                        capacity_mtpa=regas_build.capacity_mtpa)
    liq_parts = liquefaction_cost(liq)
    v = voyage(ship)
    # shipping cost is per MMBtu delivered; per MMBtu loaded it is the same
    # numerator over a larger base, so boil-off is already charged to the buyer's side.
    shipping = v["usd_per_mmbtu_delivered"]
    rg = regas_cost(regas)
    # Regas send-out is per MMBtu received, so delivered cost needs no further adjustment.
    delivered = liq_parts["fob"] + shipping + rg
    return Estimate(
        feed_gas=liq_parts["feed_gas"],
        liquefaction_capex_usd=liq_parts["capex_usd"],
        liquefaction_capital=liq_parts["capital"],
        liquefaction_opex=liq_parts["fixed_opex"],
        liquefaction_variable=liq_parts["other_variable"],
        fob_price=liq_parts["fob"],
        shipping=shipping,
        regas=rg,
        delivered=delivered,
        voyage=v,
        detail={
            "liquefaction": asdict(liq),
            "shipping": asdict(ship),
            "regas": asdict(regas),
            "bottom_up_capex": bu,
        },
    )


def _set_price(b: CapexBuild, field_name: str, value: float) -> CapexBuild:
    return replace(b, prices=replace(b.prices, **{field_name: value}))


def _set_labour_rate(b: CapexBuild, _field_name: str, value: float) -> CapexBuild:
    return replace(b, region=replace(b.region, labour_rate=value))


_Getter = Callable[[CapexBuild], float]
_Setter = Callable[[CapexBuild, str, float], CapexBuild]
# driver name -> (read current value, build a copy with the value replaced)
_SENSITIVITY_DRIVERS: dict[str, tuple[_Getter, _Setter]] = {
    "steel_usd_per_t": (lambda b: b.prices.steel_usd_per_t, _set_price),
    "cement_usd_per_t": (lambda b: b.prices.cement_usd_per_t, _set_price),
    "labour_rate": (lambda b: b.region.labour_rate, _set_labour_rate),
    "equipment_index": (lambda b: b.prices.equipment_index, _set_price),
}


def sensitivity(
    liq_build: CapexBuild,
    ship: ShippingInputs | None = None,
    regas: RegasInputs | None = None,
    liq: LiquefactionInputs | None = None,
    delta: float = 0.20,
) -> dict:
    """Change in delivered USD/MMBtu when each capex driver moves +/- `delta` (fraction).

    Returns {driver: (low_delta, high_delta)} relative to the base delivered cost,
    sorted by swing, for steel, cement, labour rate, equipment index.
    """
    base = estimate(liq, ship, regas, liq_build=liq_build).delivered

    def run(name: str, value: float) -> float:
        _, setter = _SENSITIVITY_DRIVERS[name]
        return estimate(liq, ship, regas, liq_build=setter(liq_build, name, value)).delivered - base

    out = {}
    for name, (getter, _) in _SENSITIVITY_DRIVERS.items():
        v = getter(liq_build)
        out[name] = (run(name, v * (1 - delta)), run(name, v * (1 + delta)))
    return dict(sorted(out.items(), key=lambda kv: abs(kv[1][1] - kv[1][0]), reverse=True))
