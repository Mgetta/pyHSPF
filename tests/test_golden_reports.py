
import pandas.testing as pdt
from tests.helpers.generate_goldens import load_golden
from tests.configs import ALL_MODEL_CONFIGS, CONTRIBUTION_CASES, WATERSHED_CASES, load_model
import pytest
# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("constituent", ["Q", "TSS", "TP", "TN", "OP", "TKN"])
@pytest.mark.parametrize("model_config", ALL_MODEL_CONFIGS)
def test_catchment_loading(model_config, constituent):
    """Golden for reports.get_catchment_loading via model.reports."""
    model = load_model(model_config.uci_file_path)
    df = model.reports.catchment_loading(constituent=constituent, 
                                         simulation_period='yearly')
    golden = load_golden(model_config.model_dir_path, "reports", "reports.catchment_loading",
                constituent=constituent, simulation_period='yearly')
    pdt.assert_frame_equal(df, golden)

@pytest.mark.parametrize('by_landcover', [False, True])
@pytest.mark.parametrize("constituent", ["Q", "TSS", "TP", "TN", "OP", "TKN"])
@pytest.mark.parametrize("model_config, watershed", WATERSHED_CASES)
def test_watershed_loading(model_config, watershed, constituent, by_landcover):
    """Golden for reports.get_watershed_loading via model.reports."""
    model = load_model(model_config.uci_file_path)
    
    # Extract data directly from the parameterized watershed
    reach_ids = watershed["reach_ids"]
    upstream_reach_ids = watershed.get("upstream_reach_ids")
    
    # These can also be parameterized later!
    simulation_period = 'yearly'

    df = model.reports.watershed_loading(
        constituent=constituent, 
        reach_ids=reach_ids, 
        upstream_reach_ids=upstream_reach_ids, 
        by_landcover=by_landcover, 
        simulation_period=simulation_period,
    )
    golden = load_golden(
        model_config.model_dir_path, "reports", "reports.watershed_loading",
        constituent=constituent, reach_ids=reach_ids,
        upstream_reach_ids=upstream_reach_ids,
        by_landcover=by_landcover, simulation_period=simulation_period
    )
    pdt.assert_frame_equal(df, golden)


@pytest.mark.parametrize("constituent", ["TSS", "TP", "TN", "OP", "TKN"])
@pytest.mark.parametrize("model_config, target_reach_id", CONTRIBUTION_CASES)
def test_total_contributions(model_config, target_reach_id, constituent):
    """Golden for contributions.total_contributions via model.reports."""
    model = load_model(model_config.uci_file_path)
    df = model.reports.total_contributions(constituent, target_reach_id)
    golden = load_golden(model_config.model_dir_path, "reports", "reports.total_contributions",
                constituent=constituent, target_reach_id=target_reach_id)

    pdt.assert_frame_equal(df, golden)

@pytest.mark.parametrize("constituent", ["TSS", "TP", "TN", "OP", "TKN"])
@pytest.mark.parametrize("model_config, target_reach_id", CONTRIBUTION_CASES)
def test_catchment_contributions(model_config, target_reach_id, constituent):
    """Golden for contributions.catchment_contributions via model.reports."""
    model = load_model(model_config.uci_file_path)
    df = model.reports.catchment_contributions(constituent, target_reach_id)
    golden = load_golden(model_config.model_dir_path, "reports", "reports.catchment_contributions",
                 constituent=constituent, target_reach_id=target_reach_id)
    pdt.assert_frame_equal(df, golden)
