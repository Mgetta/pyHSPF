
from dataclasses import dataclass
from hspf.model.hspfModel import hspfModel
from functools import lru_cache
from typing import List
from pathlib import Path
from tests.conftest import MODELS_DIR


TESTS_DIR = Path(__file__).parent
DATA_DIR = TESTS_DIR / "data"
MODELS_DIR = DATA_DIR / "models"

@dataclass(frozen=True)
class GoldenTestConfig:
    model_name: str
    TARGET_REACH_IDS: List[int]
    WATERSHEDS: List[dict]
    model_dir: str = MODELS_DIR
    LOADING_CONSTITUENTS: tuple = ("Q", "TSS", "TP", "TN", "OP", "TKN")
    CONTRIBUTION_CONSTITUENTS: tuple = ("TSS", "TP", "TN","OP", "TKN")
    RECIPE_OPERATIONS: tuple = ("PERLND", "IMPLND")
    RECIPE_T_CODES: tuple = (4, 5)
    GET_OPNID_OPERATIONS: tuple = ("PERLND", "IMPLND", "RCHRES")
    RAW_TIMESERIES: tuple[dict] = (
        {"operation": "PERLND", "t_code": 4, "variable": "SURO", "activity": "PWATER"},
        {"operation": "RCHRES", "t_code": 2, "variable": "ROVOL", "activity": "HYDR"},
    )

    @property
    def model_dir_path(self) -> Path:
        """Return the path to the model directory."""
        return Path(self.model_dir) / self.model_name

    @property
    def uci_file_path(self) -> Path:
        """Return the path to the UCI file."""
        return self.model_dir_path / (self.model_name + ".uci")


# Create a cached loader function
@lru_cache(maxsize=None)
def load_model(uci_file_path: Path):
    model = hspfModel(uci_file_path, run_model=False)
    return model

BlueEarth_CONFIG = GoldenTestConfig(
        model_name="BlueEarth",
        TARGET_REACH_IDS=[870],
        WATERSHEDS=[
            {"label": "outlet", "reach_ids": [870], "upstream_reach_ids": None},
        ],
            LOADING_CONSTITUENTS = ("Q", "TSS", "TP", "TN", "OP", "TKN"),
            CONTRIBUTION_CONSTITUENTS = ("TSS", "TP", "TN", "OP", "TKN"),
        RECIPE_OPERATIONS = ("PERLND", "IMPLND"),
        RECIPE_T_CODES = (4, 5),
        GET_OPNID_OPERATIONS = ("PERLND", "IMPLND", "RCHRES"),
        RAW_TIMESERIES = [
            {"operation": "PERLND", "t_code": 4, "variable": "SURO", "activity": "PWATER"},
            {"operation": "RCHRES", "t_code": 2, "variable": "ROVOL", "activity": "HYDR"},
        ])
    

LOWUS_CONFIG = GoldenTestConfig(
        model_name="LOWUS",
        TARGET_REACH_IDS=[999],
        WATERSHEDS=[
            {"label": "outlet", "reach_ids": [999], "upstream_reach_ids": None},
        ],
        LOADING_CONSTITUENTS = ("Q", "TSS", "TP", "TN", "OP", "TKN"),
        CONTRIBUTION_CONSTITUENTS = ("TSS", "TP", "TN", "OP", "TKN"),
        RECIPE_OPERATIONS = ("PERLND", "IMPLND"),
        RECIPE_T_CODES = (4, 5),
        GET_OPNID_OPERATIONS = ("PERLND", "IMPLND", "RCHRES"),
        RAW_TIMESERIES = [
            {"operation": "PERLND", "t_code": 4, "variable": "SURO", "activity": "PWATER"},
            {"operation": "RCHRES", "t_code": 2, "variable": "ROVOL", "activity": "HYDR"},
        ])

MiddleMN_CONFIG = GoldenTestConfig(
        model_name="MiddleMN",
        TARGET_REACH_IDS=[630],
        WATERSHEDS=[
            {"label": "outlet", "reach_ids": [630], "upstream_reach_ids": None},
        ],
        LOADING_CONSTITUENTS = ("Q", "TSS", "TP", "TN", "OP", "TKN"),
        CONTRIBUTION_CONSTITUENTS = ("TSS", "TP", "TN", "OP", "TKN"),
        RECIPE_OPERATIONS = ("PERLND", "IMPLND"),
        RECIPE_T_CODES = (4, 5),
        GET_OPNID_OPERATIONS = ("PERLND", "IMPLND", "RCHRES"),
        RAW_TIMESERIES = [
            {"operation": "PERLND", "t_code": 4, "variable": "SURO", "activity": "PWATER"},
            {"operation": "RCHRES", "t_code": 2, "variable": "ROVOL", "activity": "HYDR"},
        ])

ALL_MODEL_CONFIGS = [BlueEarth_CONFIG, LOWUS_CONFIG, MiddleMN_CONFIG]

CONTRIBUTION_CASES = [
    (config, target_reach_id)
    for config in ALL_MODEL_CONFIGS
    for target_reach_id in config.TARGET_REACH_IDS
]

WATERSHED_CASES = [
    (config, watershed)
    for config in ALL_MODEL_CONFIGS
    for watershed in config.WATERSHEDS
]
