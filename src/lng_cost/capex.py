"""Bottom-up capex build-up from labour, cement/concrete, steel and equipment.

Quantities are scaled from a 5 Mtpa reference plant with a capacity exponent;
unit prices and regional factors are inputs. ALL numbers here are illustrative
placeholders, not sourced benchmarks. Calibrate them (see docs/REFERENCES.md)
before relying on any output.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

REFERENCE_MTPA = 5.0


@dataclass
class PlantQuantities:
    """Physical quantities for a plant of `reference_mtpa`."""
    reference_mtpa: float = REFERENCE_MTPA
    steel_t: float = 100_000.0           # fabricated structural, piping, plate
    concrete_m3: float = 120_000.0
    labour_hours: float = 12_000_000.0   # direct craft hours at productivity 1.0
    equipment_usd: float = 2_000_000_000.0  # purchased equipment at index 1.0
    scale_exponent: float = 0.65         # materials / labour / equipment scaling


LIQUEFACTION = PlantQuantities()
REGAS = PlantQuantities(steel_t=25_000, concrete_m3=60_000,
                        labour_hours=3_000_000, equipment_usd=250_000_000)


@dataclass
class Region:
    labour_rate: float = 45.0        # USD/hour fully loaded craft rate
    productivity: float = 1.0        # 1.0 = reference; <1 means more hours per task
    material_factor: float = 1.0     # freight / local-content multiplier on steel & concrete
    equipment_factor: float = 1.0    # freight, duties, module yard multiplier


# Illustrative regions only.
REGIONS = {
    "reference": Region(),
    "us_gulf": Region(labour_rate=60, productivity=0.85, material_factor=1.00, equipment_factor=1.05),
    "middle_east": Region(labour_rate=28, productivity=0.80, material_factor=1.10, equipment_factor=1.10),
    "australia": Region(labour_rate=85, productivity=0.70, material_factor=1.15, equipment_factor=1.15),
    "east_africa": Region(labour_rate=25, productivity=0.60, material_factor=1.25, equipment_factor=1.20),
}


@dataclass
class Prices:
    steel_usd_per_t: float = 2_000.0      # fabricated & erected-ready
    cement_usd_per_t: float = 130.0
    cement_t_per_m3: float = 0.35         # cement content of structural concrete
    concrete_other_usd_per_m3: float = 150.0  # aggregate, admixtures, placement
    equipment_index: float = 1.0          # multiplies purchased equipment cost


@dataclass
class Factors:
    indirects: float = 0.25    # of direct cost: temp facilities, supervision, EPC fee
    owners: float = 0.10       # of (direct + indirects)
    contingency: float = 0.15  # of the subtotal above


@dataclass
class CapexBuild:
    capacity_mtpa: float = 5.0
    quantities: PlantQuantities = field(default_factory=PlantQuantities)
    prices: Prices = field(default_factory=Prices)
    region: Region = field(default_factory=Region)
    factors: Factors = field(default_factory=Factors)


def build_capex(b: CapexBuild) -> dict:
    """Return capex components in USD plus total and USD per tonne/yr."""
    if b.capacity_mtpa <= 0:
        raise ValueError("capacity_mtpa must be > 0")
    q, p, r, f = b.quantities, b.prices, b.region, b.factors
    s = (b.capacity_mtpa / q.reference_mtpa) ** q.scale_exponent

    steel = q.steel_t * s * p.steel_usd_per_t * r.material_factor
    concrete_unit = p.cement_t_per_m3 * p.cement_usd_per_t + p.concrete_other_usd_per_m3
    cement = q.concrete_m3 * s * p.cement_t_per_m3 * p.cement_usd_per_t * r.material_factor
    concrete_other = q.concrete_m3 * s * p.concrete_other_usd_per_m3 * r.material_factor
    labour = q.labour_hours * s / r.productivity * r.labour_rate
    equipment = q.equipment_usd * s * p.equipment_index * r.equipment_factor

    direct = steel + cement + concrete_other + labour + equipment
    indirects = direct * f.indirects
    owners = (direct + indirects) * f.owners
    contingency = (direct + indirects + owners) * f.contingency
    total = direct + indirects + owners + contingency
    return {
        "steel": steel, "cement": cement, "concrete_other": concrete_other,
        "labour": labour, "equipment": equipment, "direct": direct,
        "indirects": indirects, "owners": owners, "contingency": contingency,
        "total": total,
        "usd_per_tpa": total / (b.capacity_mtpa * 1e6),
        "concrete_usd_per_m3": concrete_unit,
    }


def with_region(b: CapexBuild, name: str) -> CapexBuild:
    try:
        return replace(b, region=REGIONS[name])
    except KeyError:
        raise ValueError(f"unknown region {name!r}; choose from {sorted(REGIONS)}") from None
