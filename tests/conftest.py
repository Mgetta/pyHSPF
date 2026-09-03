from pathlib import Path
import pytest

DATA_DIR = Path(__file__).parent / "data"
MODELS_DIR = DATA_DIR / "models"


@pytest.fixture
def tests_data_dir():
    """Path to the tests/data folder."""
    return DATA_DIR


@pytest.fixture
def model_data_dir():
    """Path to tests/data/models, where full model fixtures live."""
    return MODELS_DIR
