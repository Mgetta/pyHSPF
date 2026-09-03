"""Manually regenerate all starter goldens for one fixture model.

This is intentionally a small, editable script. Update the constants near the
top for the model/reaches/constituents you care about, then run it from the repo
root, for example:

    python tests\helpers\generate_all_goldens.py simple_monthly

The script writes under:

    tests\data\models\<model_name>\goldens\

It does not run tests and it should not be part of normal pytest execution.
"""
#%%
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

from hspf.model.hspfModel import hspfModel
from tests.helpers import generate_goldens as gg
from tests.configs import load_model, GoldenTestConfig

#%%
# from pyhcal.repository import Repository

# TEST_MODELS_DIR = REPO_ROOT / "tests" / "data" / "models"

# repo_name = 'BlueEarth'

# repo = Repository(repo_name)
# repo.copy(TEST_MODELS_DIR)


# mod = hspfModel(TEST_MODELS_DIR / repo_name / f"{repo_name}.uci", run_model=False)
# mod.uci.initialize(reach_ids = [999], n =5)
# mod.uci.write(TEST_MODELS_DIR / repo_name / f"{repo_name}.uci")


#%% EXAMPLES
# # Edit these lists as each fixture model becomes better understood.
# LOADING_CONSTITUENTS = ("Q", "TSS", "TP", "TN", "OP", "TKN")
# CONTRIBUTION_CONSTITUENTS = ("TSS", "TP", "TN")
# RECIPE_OPERATIONS = ("PERLND", "IMPLND")
# RECIPE_T_CODES = (4, 5)
# GET_OPNID_OPERATIONS = ("PERLND", "IMPLND", "RCHRES")

# # If empty, the script uses the first outlet reach for target-reach goldens.
# TARGET_REACH_IDS: List[int] = []

# # If empty, the script creates one watershed spec using the first outlet reach.
# # Add more dictionaries as needed, for example:
# #
# # WATERSHEDS = [
# #     {"label": "outlet", "reach_ids": [101], "upstream_reach_ids": None},
# #     {"label": "mid_network", "reach_ids": [52], "upstream_reach_ids": None},
# #     {"label": "local_between_gages", "reach_ids": [101], "upstream_reach_ids": [52]},
# # ]
# WATERSHEDS: List[Dict[str, object]] = []

# # Raw HBN outputs vary the most by model, so keep this explicit and editable.
# # Add entries such as:
# #
# # RAW_TIMESERIES = [
# #     {"operation": "PERLND", "t_code": 4, "variable": "SURO", "activity": "PWATER"},
# #     {"operation": "RCHRES", "t_code": 4, "variable": "ROVOL", "activity": "HYDR"},
# # ]
# RAW_TIMESERIES: List[Dict[str, object]] = []


def default_target_reaches(model_config: GoldenTestConfig) -> List[int]:
    """Use configured target reaches, or fall back to the first outlet."""
    if model_config.TARGET_REACH_IDS:
        return list(model_config.TARGET_REACH_IDS)
    model = load_model(model_config.uci_file_path)
    outlets = model.uci.network.outlets()
    if not outlets:
        raise ValueError("Model has no network outlets; set TARGET_REACH_IDS manually")
    return [sorted(outlets)[0]]


def default_watersheds(model_config: GoldenTestConfig) -> List[Dict[str, object]]:
    """Use configured watershed specs, or fall back to the first outlet."""
    
    if model_config.WATERSHEDS:
        return list(model_config.WATERSHEDS)
    model = load_model(model_config.uci_file_path)
    reach_id = default_target_reaches(model_config)[0]
    return [{"label": "first_outlet", "reach_ids": [reach_id], "upstream_reach_ids": None}]


def generate_report_goldens(model_config: GoldenTestConfig, folder: Path) -> List[Path]:
    """Generate loading and contribution report goldens."""
    model = load_model(model_config.uci_file_path)
    written: List[Path] = []

    for constituent in model_config.LOADING_CONSTITUENTS:
        written.append(gg.generate_catchment_loading(model, folder, constituent))

        for watershed in model_config.WATERSHEDS:
            reach_ids = watershed["reach_ids"]
            upstream_reach_ids = watershed.get("upstream_reach_ids")
            for by_landcover in (False, True):
                written.append(
                    gg.generate_watershed_loading(
                        model,
                        folder,
                        constituent,
                        reach_ids=reach_ids,
                        upstream_reach_ids=upstream_reach_ids,
                        by_landcover = by_landcover,
                    )
                )

    for constituent in model_config.CONTRIBUTION_CONSTITUENTS:
        for reach_id in model_config.TARGET_REACH_IDS:
            written.append(
                gg.generate_total_contributions(model, folder, constituent, reach_id)
            )
            written.append(
                gg.generate_catchment_contributions(model, folder, constituent, reach_id)
            )

    return written


def generate_recipe_goldens(model_config: GoldenTestConfig, folder: Path) -> List[Path]:
    """Generate TP/TN recipe goldens for configured operations and time codes."""
    model = load_model(model_config.uci_file_path)
    written: List[Path] = []
    for operation in model_config.RECIPE_OPERATIONS:
        for t_code in model_config.RECIPE_T_CODES:
            written.append(
                gg.generate_total_phosphorus(model, folder, operation=operation, t_code=t_code)
            )
            written.append(
                gg.generate_total_nitrogen(model, folder, operation=operation, t_code=t_code)
            )
    return written


def generate_network_goldens(model_config: GoldenTestConfig, folder: Path) -> List[Path]:
    """Generate catchment/watershed grouping and traversal goldens."""
    model = load_model(model_config.uci_file_path)
    written = [
        gg.generate_subwatersheds(model, folder),
        gg.generate_outlets(model, folder),
    ]

    for reach_id in model_config.TARGET_REACH_IDS:
        written.append(gg.generate_upstream_network(model, folder, reach_id))

    for watershed in model_config.WATERSHEDS:
        reach_ids = watershed["reach_ids"]
        upstream_reach_ids = watershed.get("upstream_reach_ids")

        written.append(
            gg.generate_watershed_area(
                model,
                folder,
                reach_ids=reach_ids,
                upstream_reach_ids=upstream_reach_ids,
            )
        )
        written.append(
            gg.generate_drainage_area_landcover(
                model,
                folder,
                reach_ids=reach_ids,
                upstream_reach_ids=upstream_reach_ids,
            )
        )

        for operation in model_config.GET_OPNID_OPERATIONS:
            written.append(
                gg.generate_get_opnids(
                    model,
                    folder,
                    operation,
                    reach_ids=reach_ids,
                    upstream_reach_ids=upstream_reach_ids,
                )
            )

    # Calibration order is most useful across all routing reaches.
    if model.uci.network.routing_reaches:
        written.append(
            gg.generate_calibration_order(model, folder, model.uci.network.routing_reaches)
        )
    return written


def generate_raw_goldens(model_config: GoldenTestConfig, folder: Path) -> List[Path]:
    """Generate configured direct-HBN-read goldens."""
    model = load_model(model_config.uci_file_path)
    written: List[Path] = []
    for spec in model_config.RAW_TIMESERIES:
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


def generate_all_for_model(model_config: GoldenTestConfig) -> List[Path]:
    """Generate all configured goldens for one fixture model name."""
    folder = model_config.model_dir_path
    written: List[Path] = []
    written.extend(generate_report_goldens(model_config, folder))
    written.extend(generate_recipe_goldens(model_config, folder))
    written.extend(generate_network_goldens(model_config, folder))
    written.extend(generate_raw_goldens(model_config, folder))
    return written

