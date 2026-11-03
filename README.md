# lng-cost: parametric LNG value-chain cost estimator

A small, dependency-free Python package that estimates the delivered cost of LNG in
USD/MMBtu as the sum of three levelized blocks: liquefaction (FOB), single-vessel
shipping, and regasification. It is a screening-level tool (roughly AACE Class 5) for
energy analysts who want a transparent, editable chain model rather than a bankable
cost; it produces a text report or JSON from a CLI, or an `Estimate` object from Python.

> Status: maintained. **All default numbers are illustrative placeholders, not sourced
> benchmarks.** Replace them with project- or quote-specific values before relying on
> any output. No proprietary cost-index data is bundled.

## What it does
- Annuitises liquefaction and regas capex with a capital-recovery factor (`crf`) and
  spreads it over annual MMBtu at a given utilisation (`model.liquefaction_cost`, `model.regas_cost`).
- Grosses feed gas up for plant fuel and loss: `feed / (1 - fuel_and_loss)`.
- Builds shipping cost from one round-trip voyage: charter days, bunkers, port time,
  canal fees and laden-leg boil-off (`model.voyage`).
- Optionally builds liquefaction (and regas) capex bottom-up from steel, cement, other
  concrete inputs, craft labour and purchased equipment, with region multipliers and
  stacked indirects / owner's cost / contingency factors (`capex.build_capex`).
- Reports the +/-20 % swing in delivered cost for each capex driver (`model.sensitivity`).
- Rescales a reference plant with the capacity-exponent ("six-tenths") rule (`model.scale_capex`).

## Quick start
```bash
git clone https://github.com/herrrickshaw/lng-cost.git
cd lng-cost
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
lng-cost --distance-nm 9000 --capex-per-tpa 1000
```

Other invocations:

```bash
lng-cost                       # defaults; delivered cost 8.49 USD/MMBtu
lng-cost --json                # full Estimate as JSON
lng-cost --bottom-up --region australia --steel-price 2400 --labour-rate 90 --sensitivity
python -m lng_cost.cli --help  # same CLI without the console script
```

From Python:

```python
from lng_cost import LiquefactionInputs, ShippingInputs, RegasInputs, estimate

e = estimate(
    LiquefactionInputs(capacity_mtpa=5, capex_per_tpa=1000, feed_gas_price=3.0),
    ShippingInputs(distance_nm=9000),
    RegasInputs(),
)
print(round(e.delivered, 2), "USD/MMBtu")
```

Bottom-up capex instead of a flat USD/tpa:

```python
from lng_cost import CapexBuild, Prices, with_region, estimate, sensitivity

b = with_region(CapexBuild(capacity_mtpa=5, prices=Prices(steel_usd_per_t=2400)), "us_gulf")
e = estimate(liq_build=b)                 # replaces flat capex_per_tpa
print(e.detail["bottom_up_capex"]["liquefaction"]["usd_per_tpa"])
print(sensitivity(b))                     # +/-20% swing per driver, sorted by swing
```

## How it works

| Stage | Module / function | Formula (USD/MMBtu unless stated) |
|---|---|---|
| Liquefaction | `model.liquefaction_cost` | `capex·CRF / annual_MMBtu` + fixed O&M + `feed/(1−fuel&loss)` + other variable |
| Shipping | `model.voyage` | `(days·charter + sea_days·burn·bunker + canal) / delivered_MMBtu` |
| Regas | `model.regas_cost` | `capex·(CRF + fixed O&M%) / annual_MMBtu` + variable |
| Delivered | `model.estimate` | liquefaction FOB + shipping + regas |
| Bottom-up capex | `capex.build_capex` | steel + cement + other concrete + labour (hours / productivity × rate) + equipment (× index), then indirects, owner's costs and contingency as stacked factors |
| Sensitivity | `model.sensitivity` | re-runs `estimate` with each driver at ±delta; returns `{driver: (low, high)}` sorted by swing |
| CLI | `cli.main` | `_inputs_from_args` → `_capex_builds_from_args` → `estimate` → `render_text` / JSON |

Design points:

- Every function in `model.py` and `capex.py` is pure (dataclasses in, numbers out);
  all I/O lives in `cli.py`.
- Inputs are frozen-style dataclasses; the CLI and `sensitivity` derive variants with
  `dataclasses.replace`, so a base scenario is never mutated.
- Bottom-up quantities scale from a 5 Mtpa reference with exponent 0.65. Regions
  (`reference`, `us_gulf`, `middle_east`, `australia`, `east_africa`) set wage,
  productivity, and material/equipment multipliers; `with_region` selects one.
- With default quantities, equipment and labour dominate the capex build-up; cement is a
  rounding error for delivered cost (about 0.001 USD/MMBtu per 20 %), which is typical
  but depends on your quantities.
- Constants: 52 MMBtu per tonne LNG (HHV, typically 51–54 by composition) and
  0.45 t/m³ LNG density. Costs are real, constant USD; no tax, royalty, inflation,
  financing-during-construction or contingency beyond what you put in capex.
- Shipping is charged per MMBtu *delivered*, so boil-off is already on the buyer's side
  and regas needs no further adjustment.

## Repository layout
| Path | Purpose |
|---|---|
| `src/lng_cost/model.py` | Pure chain model: `crf`, `scale_capex`, input dataclasses, `liquefaction_cost`, `voyage`, `regas_cost`, `estimate`, `sensitivity` |
| `src/lng_cost/capex.py` | Bottom-up capex: `PlantQuantities`, `Prices`, `Region`, `Factors`, `CapexBuild`, `REGIONS`, `build_capex`, `with_region` |
| `src/lng_cost/cli.py` | `lng-cost` console script: argparse → inputs → `estimate` → text/JSON |
| `src/lng_cost/__init__.py` | Public API re-exports |
| `tests/` | `test_model.py` (unit), `test_regression.py` (pinned numeric outputs), `test_cli.py` (CLI smoke) |
| `docs/REFERENCES.md` | Literature leads for calibrating quantities and prices |
| `pyproject.toml` | Packaging, `ruff` and `pytest` configuration |
| `.github/workflows/ci.yml` | `ruff check` + `pytest` on Python 3.9 and 3.12 |

No data files are tracked; the model has no external inputs.

## Data sources and literature

The repository ships no third-party data. Defaults are placeholders; the methods are standard:

| Topic | Reference | Use here |
|---|---|---|
| Capacity-exponent scaling | Williams, R. "Six-Tenths Factor Aids in Approximating Costs", *Chemical Engineering*, 1947 | `scale_capex` and `PlantQuantities.scale_exponent` (0.65 default) |
| Estimate classes | AACE International RP 18R-97, cost estimate classification system | "Class 5 / screening" accuracy claim |
| LNG energy content and density | GIIGNL, *LNG Information Paper No. 1: Basic Properties of LNG* | 52 MMBtu/t, 0.45 t/m³ |
| Calibration leads (unverified) | [docs/REFERENCES.md](docs/REFERENCES.md): Songhurst (OIES) 2014–18 cost trends, Cao et al. 2021 (Energy 237), Columbia CCSI Open LNG Regasification Model, DIW datadoc 2019-100, and others | Quantities, unit prices, charter rates |

`docs/REFERENCES.md` is explicit that its entries are search leads not yet read or
verified; no figure in this repository is taken from them.

Commercial cost indices (S&P Global, IHS and similar) are proprietary and must not be
committed. If you hold a licence, calibrate by overriding the input dataclasses from your
own copy and keep that data out of the public repo.

## Configuration

There are no environment variables, config files or secrets. All parameters are
dataclass fields with defaults in `model.py` (`LiquefactionInputs`, `ShippingInputs`,
`RegasInputs`) and `capex.py` (`PlantQuantities`, `Prices`, `Region`, `Factors`), each
with its unit in a trailing comment. CLI flags override a subset of them
(`lng-cost --help`); `--capacity-mtpa` and `--discount-rate` apply to both liquefaction
and regas, and `--sensitivity` implies `--bottom-up`.

## Testing
```bash
pip install -e .[dev]
ruff check src tests
pytest -q          # 24 tests
```

`tests/test_regression.py` pins the numeric outputs of the default and README scenarios;
change those expectations only when the model is intentionally changed.

## Limitations and known issues
- Defaults are not benchmarks; the output is only as good as the inputs you supply.
- Single-vessel voyage economics; no fleet sizing, idle time or spot/charter mix.
- No terminal tank/jetty detail, no pipeline or upstream development cost.
- No uncertainty analysis beyond the one-at-a-time `sensitivity`; Monte Carlo is left to the caller.
- Laden-leg boil-off is capped at 50 % of cargo (`MAX_BOIL_OFF_FRACTION`); no reliquefaction or boil-off-as-fuel credit.
- `scale_capex` and `build_capex` are independent routes; `estimate` uses one or the other, never both.

## Licence
MIT (see `LICENSE`).
