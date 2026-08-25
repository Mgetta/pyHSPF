# HSPF fixture models

Put small, self-contained model fixtures here:

```text
tests/data/models/<model_name>/
├── <model_name>.uci
├── <input>.wdm
├── <output>.hbn
└── goldens/
    ├── raw/
    ├── recipes/
    ├── reports/
    └── network/
```

Keep this simple:

1. The UCI `FILES` block should reference files in this same model folder using
   relative paths.
2. Commit the HBN files. The test suite should compare existing outputs, not run
   WinHSPF.
3. Start with one small trimmed model, then add more fixtures only when they cover
   behavior the first model does not.
4. Goldens live beside the model that produced them.

Use `_template/` as a copy/paste starting point.

## Regenerating goldens manually

Each golden has its own `generate_*` function in
`tests/helpers/generate_goldens.py`. Run the ones you care about from a Python
session or small scratch script:

```python
from hspf.hspfModel import hspfModel
from tests.helpers import generate_goldens as gg

model_dir = r"tests\data\models\simple_monthly"
model = hspfModel(r"tests\data\models\simple_monthly\simple_monthly.uci")

# reports
gg.generate_catchment_loading(model, model_dir, "TP")
gg.generate_watershed_loading(model, model_dir, "TP", reach_ids=[10])
gg.generate_total_contributions(model, model_dir, "TP", target_reach_id=10)

# recipes
gg.generate_total_phosphorus(model, model_dir, operation="PERLND", t_code=4)
gg.generate_total_nitrogen(model, model_dir, operation="PERLND", t_code=4)

# network
gg.generate_subwatersheds(model, model_dir)
gg.generate_get_opnids(model, model_dir, "PERLND", reach_ids=[10])
gg.generate_upstream_network(model, model_dir, reach_id=10)
gg.generate_watershed_area(model, model_dir, reach_ids=[10])

# raw HBN output
gg.generate_raw_timeseries(model, model_dir, "PERLND", 4, "SURO", activity="PWATER")
```

Each function writes one CSV into the matching `goldens/` subfolder:

- `goldens/reports/` — loading and contribution reports;
- `goldens/recipes/` — MASS-LINK-derived nutrients (TP/TN);
- `goldens/network/` — catchment/watershed grouping and traversal results;
- `goldens/raw/` — direct HBN timeseries reads.

When you add a model, pick 2-3 representative reaches (an outlet from
`model.uci.network.outlets()`, one mid-network, one at or below a lake if the
model has one) and generate the reach-scoped goldens for each.
