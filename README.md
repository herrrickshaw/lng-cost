# lng-cost

A small, dependency-free Python module for **parametric LNG value-chain cost estimates**:
liquefaction → shipping → regasification → delivered cost in USD/MMBtu.

Capital is annuitised with a capital-recovery factor (CRF); feed gas is grossed up for
plant fuel and loss; shipping is built from a round-trip voyage (charter, bunkers, port
time, boil-off); regas is a levelized terminal charge.

> **Defaults are illustrative placeholders, not sourced benchmarks.** Replace them with
> project- or quote-specific numbers. Accuracy is a screening-level (roughly Class 5)
> estimate, not a bankable cost.

## Install

```bash
pip install -e .[dev]
pytest
```

## Use

```python
from lng_cost import LiquefactionInputs, ShippingInputs, RegasInputs, estimate

e = estimate(
    LiquefactionInputs(capacity_mtpa=5, capex_per_tpa=1000, feed_gas_price=3.0),
    ShippingInputs(distance_nm=9000),
    RegasInputs(),
)
print(round(e.delivered, 2), "USD/MMBtu")
```

CLI:

```bash
lng-cost --distance-nm 9000 --capex-per-tpa 1000
lng-cost --json
```

## Bottom-up capex (labour, cement, steel, equipment)

Instead of a flat USD/tpa, build capex from physical quantities and unit prices:

```python
from lng_cost import CapexBuild, Prices, with_region, estimate, sensitivity

b = with_region(CapexBuild(capacity_mtpa=5, prices=Prices(steel_usd_per_t=2400)), "us_gulf")
e = estimate(liq_build=b)                 # replaces flat capex_per_tpa
print(e.detail["bottom_up_capex"]["liquefaction"]["usd_per_tpa"])
print(sensitivity(b))                     # +/-20% swing per driver
```

```bash
lng-cost --bottom-up --region australia --steel-price 2400 --labour-rate 90 --sensitivity
```

Capex = steel + cement + other concrete inputs + labour (hours / productivity x rate) +
equipment (x index), then indirects, owner's costs and contingency as stacked factors.
Quantities scale from a 5 Mtpa reference with exponent 0.65. Regions
(`reference`, `us_gulf`, `middle_east`, `australia`, `east_africa`) set wage,
productivity, and material/equipment multipliers. **All quantities, prices and regions
are placeholders**; see [docs/REFERENCES.md](docs/REFERENCES.md) for calibration leads.

With defaults, equipment and labour dominate; cement is a rounding error for delivered
cost (~0.001 USD/MMBtu per 20%), which is typical but depends on your quantities.

## Model summary

| Block | Cost per MMBtu |
|---|---|
| Liquefaction | `capex·CRF / annual_MMBtu` + fixed O&M + `feed/(1−fuel&loss)` + other variable |
| Shipping | `(days·charter + sea_days·burn·bunker + canal) / delivered_MMBtu` |
| Regas | `capex·(CRF + fixed O&M%) / annual_MMBtu + variable` |

Assumes 52 MMBtu/tonne and 0.45 t/m³. Costs are real/constant USD; no tax, royalty,
inflation, financing-during-construction or contingency beyond what you put in capex.

`scale_capex()` applies the six-tenths-style rule to rescale a reference plant.

## Calibrating to benchmarks

No third-party benchmark data (e.g. S&P Global, IHS, or similar subscription cost
indices) is bundled: it is proprietary and not redistributable. If you hold a licence,
calibrate by overriding the input dataclasses (capex per tpa, charter rates, etc.)
from your own copy, and keep that data out of the public repo.

## Limitations

- Single vessel voyage economics; no fleet sizing or idle time.
- No terminal-tank/jetty detail, no pipeline or upstream development cost.
- No uncertainty analysis; run sensitivities by looping over inputs.

## License

MIT
