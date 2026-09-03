
import pytest
import pandas.testing as pdt

from tests.configs import ALL_MODEL_CONFIGS, GoldenTestConfig, load_model
from tests.helpers.cases import Case, case_id, cases, compute_case
from tests.helpers.goldens import (
    GOLDEN_GROUPS,
    normalize_frame,
    load_golden,
    compute_case,
)


ALL_CASES = [
    (config, case)
    for config in ALL_MODEL_CONFIGS
    for case in cases(config)
]

def assert_case_matches_golden(model, config: GoldenTestConfig, case: Case) -> None:
    """Compute one case and compare it to the saved golden."""
    actual = normalize_frame(compute_case(model, case), sort_by=case.sort_by)
    expected = normalize_frame(load_golden(config, case), sort_by=case.sort_by)
    pdt.assert_frame_equal(
        actual,
        expected,
        check_dtype=False,
        check_like=False,
        rtol=1e-8,
        atol=1e-10,
    )


@pytest.mark.parametrize(
    "config, case",
    ALL_CASES,
    ids=[case_id(case) for _, case in ALL_CASES],
)
def test_golden(config, case):
    model = load_model(config.uci_file_path)
    assert_case_matches_golden(model, config, case)




@pytest.mark.parametrize("config", ALL_MODEL_CONFIGS)
def test_golden_files_match_cases(config):
    expected = {
        config.golden_path(case)
        for case in cases(config)
    }

    actual = {
        path
        for group in GOLDEN_GROUPS
        for path in (config.goldens_dir_path / group).glob("*.parquet")
    }

    missing = expected - actual
    orphaned = actual - expected

    assert not missing, f"Missing golden files: {sorted(missing)}"
    assert not orphaned, f"Orphaned golden files: {sorted(orphaned)}"