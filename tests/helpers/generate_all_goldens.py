"""Manually regenerate all starter goldens for one fixture model.

This is intentionally a small, editable script. Update the constants near the
top for the model/reaches/constituents you care about, then run it from the repo
root, for example:

    python tests\helpers\generate_all_goldens.py simple_monthly

The script writes under:

    tests\data\models\<model_name>\goldens\

It does not run tests and it should not be part of normal pytest execution.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
for path in (REPO_ROOT, SRC_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from hspf.hspfModel import hspfModel

from tests.helpers import generate_goldens as gg


TEST_MODELS_DIR = REPO_ROOT / "tests" / "data" / "models"

# Edit these lists as each fixture model becomes better understood.
LOADING_CONSTITUENTS = ("Q", "TSS", "TP", "TN", "OP", "TKN")
CONTRIBUTION_CONSTITUENTS = ("TSS", "TP", "TN")
RECIPE_OPERATIONS = ("PERLND", "IMPLND")
RECIPE_T_CODES = (4, 5)
GET_OPNID_OPERATIONS = ("PERLND", "IMPLND", "RCHRES")

# If empty, the script uses the first outlet reach for target-reach goldens.
TARGET_REACH_IDS: List[int] = []

# If empty, the script creates one watershed spec using the first outlet reach.
# Add more dictionaries as needed, for example:
#
# WATERSHEDS = [
#     {"label": "outlet", "reach_ids": [101], "upstream_reach_ids": None},
#     {"label": "mid_network", "reach_ids": [52], "upstream_reach_ids": None},
#     {"label": "local_between_gages", "reach_ids": [101], "upstream_reach_ids": [52]},
# ]
WATERSHEDS: List[Dict[str, object]] = []

# Raw HBN outputs vary the most by model, so keep this explicit and editable.
# Add entries such as:
#
# RAW_TIMESERIES = [
#     {"operation": "PERLND", "t_code": 4, "variable": "SURO", "activity": "PWATER"},
#     {"operation": "RCHRES", "t_code": 4, "variable": "ROVOL", "activity": "HYDR"},
# ]
RAW_TIMESERIES: List[Dict[str, object]] = []


def model_dir(model_name: str, models_dir: Path = TEST_MODELS_DIR) -> Path:
    """Return the folder for a named fixture model."""
    return Path(models_dir) / model_name


def find_uci_file(folder: Path) -> Path:
    """Find the single UCI file in a fixture model folder."""
    uci_files = sorted(Path(folder).glob("*.uci"))
    if not uci_files:
        raise FileNotFoundError(f"No .uci file found in {folder}")
    if len(uci_files) > 1:
        raise ValueError(f"Expected one .uci file in {folder}, found {len(uci_files)}")
    return uci_files[0]


def load_model(folder: Path):
    """Load one fixture model without requiring callers to know the UCI filename."""
    return hspfModel(str(find_uci_file(folder)), run_model=False)


def default_target_reaches(model) -> List[int]:
    """Use configured target reaches, or fall back to the first outlet."""
    if TARGET_REACH_IDS:
        return list(TARGET_REACH_IDS)

    outlets = model.uci.network.outlets()
    if not outlets:
        raise ValueError("Model has no network outlets; set TARGET_REACH_IDS manually")
    return [sorted(outlets)[0]]


def default_watersheds(model) -> List[Dict[str, object]]:
    """Use configured watershed specs, or fall back to the first outlet."""
    if WATERSHEDS:
        return list(WATERSHEDS)

    reach_id = default_target_reaches(model)[0]
    return [{"label": "first_outlet", "reach_ids": [reach_id], "upstream_reach_ids": None}]


def generate_report_goldens(model, folder: Path) -> List[Path]:
    """Generate loading and contribution report goldens."""
    written: List[Path] = []

    for constituent in LOADING_CONSTITUENTS:
        written.append(gg.generate_catchment_loading(model, folder, constituent))

        for watershed in default_watersheds(model):
            reach_ids = watershed["reach_ids"]
            upstream_reach_ids = watershed.get("upstream_reach_ids")
            label = watershed.get("label")
            written.append(
                gg.generate_watershed_loading(
                    model,
                    folder,
                    constituent,
                    reach_ids=reach_ids,
                    upstream_reach_ids=upstream_reach_ids,
                    label=label,
                )
            )

    for constituent in CONTRIBUTION_CONSTITUENTS:
        for reach_id in default_target_reaches(model):
            written.append(
                gg.generate_total_contributions(model, folder, constituent, reach_id)
            )
            written.append(
                gg.generate_catchment_contributions(model, folder, constituent, reach_id)
            )

    return written


def generate_recipe_goldens(model, folder: Path) -> List[Path]:
    """Generate TP/TN recipe goldens for configured operations and time codes."""
    written: List[Path] = []
    for operation in RECIPE_OPERATIONS:
        for t_code in RECIPE_T_CODES:
            written.append(
                gg.generate_total_phosphorus(model, folder, operation=operation, t_code=t_code)
            )
            written.append(
                gg.generate_total_nitrogen(model, folder, operation=operation, t_code=t_code)
            )
    return written


def generate_network_goldens(model, folder: Path) -> List[Path]:
    """Generate catchment/watershed grouping and traversal goldens."""
    written = [
        gg.generate_subwatersheds(model, folder),
        gg.generate_outlets(model, folder),
    ]

    for reach_id in default_target_reaches(model):
        written.append(gg.generate_upstream_network(model, folder, reach_id))

    for watershed in default_watersheds(model):
        reach_ids = watershed["reach_ids"]
        upstream_reach_ids = watershed.get("upstream_reach_ids")
        label = watershed.get("label")

        written.append(
            gg.generate_watershed_area(
                model,
                folder,
                reach_ids=reach_ids,
                upstream_reach_ids=upstream_reach_ids,
                label=label,
            )
        )
        written.append(
            gg.generate_drainage_area_landcover(
                model,
                folder,
                reach_ids=reach_ids,
                upstream_reach_ids=upstream_reach_ids,
                label=label,
            )
        )

        for operation in GET_OPNID_OPERATIONS:
            written.append(
                gg.generate_get_opnids(
                    model,
                    folder,
                    operation,
                    reach_ids=reach_ids,
                    upstream_reach_ids=upstream_reach_ids,
                    label=label,
                )
            )

    # Calibration order is most useful across all routing reaches.
    if model.uci.network.routing_reaches:
        written.append(
            gg.generate_calibration_order(model, folder, model.uci.network.routing_reaches)
        )
    return written


def generate_raw_goldens(model, folder: Path) -> List[Path]:
    """Generate configured direct-HBN-read goldens."""
    written: List[Path] = []
    for spec in RAW_TIMESERIES:
        written.append(
            gg.generate_raw_timeseries(
                model,
                folder,
                operation=spec["operation"],
                t_code=spec["t_code"],
                variable=spec["variable"],
                activity=spec.get("activity"),
            )
        )
    return written


def generate_all_for_model(model_name: str, models_dir: Path = TEST_MODELS_DIR) -> List[Path]:
    """Generate all configured goldens for one fixture model name."""
    folder = model_dir(model_name, models_dir)
    if not folder.exists():
        raise FileNotFoundError(f"Fixture model folder does not exist: {folder}")

    model = load_model(folder)
    written: List[Path] = []
    written.extend(generate_report_goldens(model, folder))
    written.extend(generate_recipe_goldens(model, folder))
    written.extend(generate_network_goldens(model, folder))
    written.extend(generate_raw_goldens(model, folder))
    return written


def parse_args(argv: Optional[Iterable[str]] = None):
    parser = argparse.ArgumentParser(
        description="Manually regenerate starter goldens for one fixture model."
    )
    parser.add_argument(
        "model_name",
        help="Folder name under tests\\data\\models, e.g. simple_monthly",
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=TEST_MODELS_DIR,
        help="Override the fixture model root folder.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    written = generate_all_for_model(args.model_name, args.models_dir)
    print(f"Wrote {len(written)} golden files:")
    for path in written:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
