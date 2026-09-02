# Template fixture model

Copy this folder to `tests/data/models/<your_model_name>/`, then add:

- one `.uci` file;
- the `.wdm` input files referenced by the UCI `FILES` block;
- the `.hbn` output files referenced by the UCI `FILES` block;
- manually reviewed golden files under `goldens/`.

The helper functions in `tests/helpers/generate_goldens.py` can regenerate the
golden files once the model folder is populated.
