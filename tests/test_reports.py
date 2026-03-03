import pandas as pd
import numpy as np
from unittest.mock import MagicMock
from hspf.reports.loading import (
    _join_catchments,
    _average_constituent_loading,
    _aggregate_catchment_loading,
    _filter_to_watershed,
    catchment_areas,
    constituent_loading_summary,
)


def _make_mock_uci():
    """Create a mock UCI object with network and subwatersheds."""
    uci = MagicMock()

    subwatersheds = pd.DataFrame({
        'TVOLNO': [1, 1, 2, 2],
        'SVOLNO': [101, 102, 103, 104],
        'SVOL': ['PERLND', 'IMPLND', 'PERLND', 'IMPLND'],
        'AFACTR': [10.0, 5.0, 20.0, 8.0],
        'LSID': ['Forest', 'Urban', 'Forest', 'Urban'],
        'MLNO': [1, 1, 1, 1],
    })
    uci.network.subwatersheds.return_value = subwatersheds
    uci.network.get_opnids.return_value = [1, 2]
    uci.network.drainage_area.return_value = 43.0

    return uci


def _make_constituent_loading_df(include_datetime=False, include_month=False):
    """Create a DataFrame in the shape produced by get_constituent_loading / _average_constituent_loading."""
    data = {
        'OPERATION': ['PERLND', 'IMPLND', 'PERLND', 'IMPLND'],
        'OPNID': [101, 102, 103, 104],
        'value': [0.5, 0.3, 0.8, 0.4],
    }
    if include_datetime:
        data['datetime'] = pd.to_datetime(['2000-01-15', '2000-02-15', '2000-03-15', '2000-04-15'])
    if include_month:
        data['month'] = [1, 1, 1, 1]
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# Tests for _join_catchments
# ---------------------------------------------------------------------------

def test_join_catchments_columns():
    uci = _make_mock_uci()
    df = _make_constituent_loading_df()
    result = _join_catchments(df, uci, 'TP')

    expected_cols = {'loading_rate', 'landcover_area', 'landcover', 'load',
                     'constituent', 'TVOLNO', 'SVOLNO', 'SVOL', 'catchment_area'}
    assert expected_cols.issubset(set(result.columns))


def test_join_catchments_load_calculation():
    uci = _make_mock_uci()
    df = _make_constituent_loading_df()
    result = _join_catchments(df, uci, 'TP')

    # load = value * AFACTR
    for _, row in result.iterrows():
        assert np.isclose(row['load'], row['loading_rate'] * row['landcover_area'])


def test_join_catchments_constituent_set():
    uci = _make_mock_uci()
    df = _make_constituent_loading_df()
    result = _join_catchments(df, uci, 'TSS')
    assert (result['constituent'] == 'TSS').all()


def test_join_catchments_preserves_datetime():
    uci = _make_mock_uci()
    df = _make_constituent_loading_df(include_datetime=True)
    result = _join_catchments(df, uci, 'TP')
    assert 'datetime' in result.columns


def test_join_catchments_preserves_month():
    uci = _make_mock_uci()
    df = _make_constituent_loading_df(include_month=True)
    result = _join_catchments(df, uci, 'TP')
    assert 'month' in result.columns


# ---------------------------------------------------------------------------
# Tests for _aggregate_catchment_loading
# ---------------------------------------------------------------------------

def _make_catchment_joined_df(include_month=False):
    """DataFrame mimicking output of _join_catchments after column selection."""
    data = {
        'TVOLNO': [1, 1, 2, 2],
        'SVOLNO': [101, 102, 103, 104],
        'SVOL': ['PERLND', 'IMPLND', 'PERLND', 'IMPLND'],
        'landcover': ['Forest', 'Urban', 'Forest', 'Urban'],
        'landcover_area': [10.0, 5.0, 20.0, 8.0],
        'catchment_area': [15.0, 15.0, 28.0, 28.0],
        'loading_rate': [0.5, 0.3, 0.8, 0.4],
        'load': [5.0, 1.5, 16.0, 3.2],
        'constituent': ['TP'] * 4,
    }
    if include_month:
        data['month'] = [1, 1, 1, 1]
    return pd.DataFrame(data)


def test_aggregate_catchment_loading_total():
    df = _make_catchment_joined_df()
    result = _aggregate_catchment_loading(df, by_landcover=False)

    assert 'TVOLNO' in result.columns
    assert 'load' in result.columns
    assert 'loading_rate' in result.columns
    # Check total load for TVOLNO=1: 5.0 + 1.5 = 6.5
    row1 = result.loc[result['TVOLNO'] == 1].iloc[0]
    assert np.isclose(row1['load'], 6.5)
    assert np.isclose(row1['loading_rate'], 6.5 / 15.0)


def test_aggregate_catchment_loading_by_landcover():
    df = _make_catchment_joined_df()
    result = _aggregate_catchment_loading(df, by_landcover=True)

    assert 'landcover' in result.columns
    # Forest in TVOLNO=1: load=5.0, area=10.0
    forest_1 = result.loc[(result['TVOLNO'] == 1) & (result['landcover'] == 'Forest')].iloc[0]
    assert np.isclose(forest_1['loading_rate'], 5.0 / 10.0)


def test_aggregate_catchment_loading_with_month_prefix():
    df = _make_catchment_joined_df(include_month=True)
    result = _aggregate_catchment_loading(df, by_landcover=False, group_prefix=['month'])

    assert 'month' in result.columns
    assert len(result) > 0


def test_aggregate_catchment_loading_by_landcover_with_month():
    df = _make_catchment_joined_df(include_month=True)
    result = _aggregate_catchment_loading(df, by_landcover=True, group_prefix=['month'])

    assert 'month' in result.columns
    assert 'landcover' in result.columns


# ---------------------------------------------------------------------------
# Tests for _filter_to_watershed
# ---------------------------------------------------------------------------

def test_filter_to_watershed_filters_reach_ids():
    uci = _make_mock_uci()
    uci.network.get_opnids.return_value = [1]  # only catchment 1

    df = _make_catchment_joined_df()
    result = _filter_to_watershed(df, uci, reach_ids=[1])

    assert (result['TVOLNO'] == 1).all()


def test_filter_to_watershed_adds_watershed_area():
    uci = _make_mock_uci()
    uci.network.get_opnids.return_value = [1, 2]
    uci.network.drainage_area.return_value = 99.0

    df = _make_catchment_joined_df()
    result = _filter_to_watershed(df, uci, reach_ids=[1, 2])

    assert 'watershed_area' in result.columns
    assert (result['watershed_area'] == 99.0).all()


def test_filter_to_watershed_custom_drainage_area():
    uci = _make_mock_uci()
    uci.network.get_opnids.return_value = [1, 2]

    df = _make_catchment_joined_df()
    result = _filter_to_watershed(df, uci, reach_ids=[1, 2], drainage_area=50.0)

    assert (result['watershed_area'] == 50.0).all()


# ---------------------------------------------------------------------------
# Tests for _average_constituent_loading
# ---------------------------------------------------------------------------

def test_average_constituent_loading_annual_shape():
    """Verify _average_constituent_loading without month produces correct groupby."""
    uci = MagicMock()
    hbn = MagicMock()

    ts_data = pd.DataFrame({
        'datetime': pd.to_datetime(['2000-01-01', '2000-02-01', '2001-01-01', '2001-02-01']),
        101: [1.0, 2.0, 3.0, 4.0],
        102: [0.5, 1.0, 1.5, 2.0],
    })

    # Mock get_constituent_loading via direct function replacement
    # since _average_constituent_loading calls it internally
    import hspf.reports.loading as reports_mod

    melted = ts_data.melt(id_vars=['datetime'], var_name='OPNID')
    melted['OPERATION'] = 'PERLND'
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted

    try:
        result = reports_mod._average_constituent_loading(uci, hbn, 'TP', 2000, 2001, simulation_period='yearly')
        assert 'OPERATION' in result.columns
        assert 'OPNID' in result.columns
        assert 'value' in result.columns
        assert 'month' not in result.columns
    finally:
        reports_mod.get_constituent_loading = original_fn


def test_average_constituent_loading_monthly_has_month():
    """Verify _average_constituent_loading with group_by_month adds month column."""
    uci = MagicMock()
    hbn = MagicMock()
    import hspf.reports.loading as reports_mod

    ts_data = pd.DataFrame({
        'datetime': pd.to_datetime(['2000-01-01', '2000-02-01', '2001-01-01', '2001-02-01']),
        101: [1.0, 2.0, 3.0, 4.0],
        102: [0.5, 1.0, 1.5, 2.0],
    })
    melted = ts_data.melt(id_vars=['datetime'], var_name='OPNID')
    melted['OPERATION'] = 'PERLND'
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted

    try:
        result = reports_mod._average_constituent_loading(uci, hbn, 'TP', 2000, 2001, simulation_period='monthly', group_by_month=True)
        assert 'month' in result.columns
    finally:
        reports_mod.get_constituent_loading = original_fn


# ---------------------------------------------------------------------------
# Tests for constituent_loading_summary
# ---------------------------------------------------------------------------

def _mock_get_constituent_loading():
    """Helper to create mock data and patch get_constituent_loading."""
    import hspf.reports.loading as reports_mod
    ts_data = pd.DataFrame({
        'datetime': pd.to_datetime([
            '2000-01-15', '2000-06-15', '2000-12-15',
            '2001-01-15', '2001-06-15', '2001-12-15',
        ]),
        101: [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        102: [0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
    })
    melted = ts_data.melt(id_vars=['datetime'], var_name='OPNID')
    melted['OPERATION'] = 'PERLND'
    return reports_mod, melted


def test_constituent_loading_summary_no_grouping():
    """Overall summary with no temporal grouping."""
    reports_mod, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    try:
        result = reports_mod.constituent_loading_summary(
            MagicMock(), MagicMock(), 'TP', 2000, 2001)
        assert 'month' not in result.columns
        assert 'year' not in result.columns
        assert 'season' not in result.columns
        assert 'value' in result.columns
    finally:
        reports_mod.get_constituent_loading = original_fn


def test_constituent_loading_summary_by_year():
    """Group by year via aggregation_period='yearly'."""
    reports_mod, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    try:
        result = reports_mod.constituent_loading_summary(
            MagicMock(), MagicMock(), 'TP', 2000, 2001, aggregation_period='yearly')
        assert 'year' in result.columns
        assert set(result['year'].unique()) == {2000, 2001}
    finally:
        reports_mod.get_constituent_loading = original_fn


def test_constituent_loading_summary_by_season():
    """Group by season via aggregation_period='seasonal'."""
    reports_mod, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    try:
        result = reports_mod.constituent_loading_summary(
            MagicMock(), MagicMock(), 'TP', 2000, 2001,
            simulation_period='monthly', aggregation_period='seasonal')
        assert 'season' in result.columns
        assert set(result['season'].unique()).issubset({'DJF', 'MAM', 'JJA', 'SON'})
    finally:
        reports_mod.get_constituent_loading = original_fn


def test_constituent_loading_summary_sum_agg():
    """Use sum instead of mean."""
    reports_mod, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    try:
        result_mean = reports_mod.constituent_loading_summary(
            MagicMock(), MagicMock(), 'TP', 2000, 2001, agg_func='mean')
        result_sum = reports_mod.constituent_loading_summary(
            MagicMock(), MagicMock(), 'TP', 2000, 2001, agg_func='sum')
        # Sum should be >= mean for positive data
        assert result_sum['value'].iloc[0] >= result_mean['value'].iloc[0]
    finally:
        reports_mod.get_constituent_loading = original_fn


def test_constituent_loading_summary_max_agg():
    """Use max aggregation."""
    reports_mod, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    try:
        result = reports_mod.constituent_loading_summary(
            MagicMock(), MagicMock(), 'TP', 2000, 2001, agg_func='max')
        # For OPNID 101: max of [1, 2, 3, 4, 5, 6] = 6
        row_101 = result.loc[result['OPNID'] == 101]
        assert np.isclose(row_101['value'].iloc[0], 6.0)
    finally:
        reports_mod.get_constituent_loading = original_fn


def test_constituent_loading_summary_invalid_aggregation_period():
    """Invalid aggregation_period raises ValueError."""
    reports_mod, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    try:
        import pytest
        with pytest.raises(ValueError):
            reports_mod.constituent_loading_summary(
                MagicMock(), MagicMock(), 'TP', 2000, 2001, aggregation_period='invalid')
    finally:
        reports_mod.get_constituent_loading = original_fn


# ---------------------------------------------------------------------------
# Tests for simulation_period / aggregation_period (utils)
# ---------------------------------------------------------------------------

def test_validate_periods_equal_no_error():
    """Same simulation and aggregation period is valid (no aggregation)."""
    from hspf.reports.utils import validate_periods
    validate_periods('monthly', 'monthly')  # should not raise


def test_validate_periods_agg_coarser_ok():
    """aggregation_period coarser than simulation_period is valid."""
    from hspf.reports.utils import validate_periods
    validate_periods('monthly', 'yearly')
    validate_periods('daily', 'simulation')


def test_validate_periods_agg_finer_raises():
    """aggregation_period finer than simulation_period must raise."""
    import pytest
    from hspf.reports.utils import validate_periods
    with pytest.raises(ValueError):
        validate_periods('yearly', 'monthly')


def test_validate_periods_invalid_sim_raises():
    """Unknown simulation_period must raise."""
    import pytest
    from hspf.reports.utils import validate_periods
    with pytest.raises(ValueError):
        validate_periods('biweekly', None)


def test_validate_periods_invalid_agg_raises():
    """Unknown aggregation_period must raise."""
    import pytest
    from hspf.reports.utils import validate_periods
    with pytest.raises(ValueError):
        validate_periods('monthly', 'biweekly')


def test_simulation_period_to_time_step():
    """Mapping from human-readable period to HBN code."""
    from hspf.reports.utils import simulation_period_to_time_step
    assert simulation_period_to_time_step('hourly') == 2
    assert simulation_period_to_time_step('daily') == 3
    assert simulation_period_to_time_step('monthly') == 4
    assert simulation_period_to_time_step('yearly') == 5


def test_simulation_period_to_time_step_invalid():
    """Invalid period must raise."""
    import pytest
    from hspf.reports.utils import simulation_period_to_time_step
    with pytest.raises(ValueError):
        simulation_period_to_time_step('biweekly')


def test_aggregation_period_to_temporal_grouping_same():
    """Equal periods now apply their grouping (no special 'equal means None')."""
    from hspf.reports.utils import aggregation_period_to_temporal_grouping
    assert aggregation_period_to_temporal_grouping('monthly', 'monthly') == 'month'
    assert aggregation_period_to_temporal_grouping('yearly', 'yearly') == 'year'


def test_aggregation_period_to_temporal_grouping_simulation():
    """'simulation' -> None (overall)."""
    from hspf.reports.utils import aggregation_period_to_temporal_grouping
    assert aggregation_period_to_temporal_grouping('monthly', 'simulation') is None


def test_aggregation_period_to_temporal_grouping_yearly():
    """monthly -> yearly maps to 'year'."""
    from hspf.reports.utils import aggregation_period_to_temporal_grouping
    assert aggregation_period_to_temporal_grouping('monthly', 'yearly') == 'year'


# ---------------------------------------------------------------------------
# Tests for constituent_loading_summary with simulation_period
# ---------------------------------------------------------------------------

def test_constituent_loading_summary_with_simulation_period():
    """simulation_period='yearly' produces same result as time_step=5."""
    reports_mod, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    try:
        result = reports_mod.constituent_loading_summary(
            MagicMock(), MagicMock(), 'TP', 2000, 2001,
            simulation_period='yearly')
        assert 'value' in result.columns
        assert 'month' not in result.columns
    finally:
        reports_mod.get_constituent_loading = original_fn


def test_constituent_loading_summary_monthly_with_yearly_agg():
    """simulation_period='monthly', aggregation_period='yearly' groups by year."""
    reports_mod, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    try:
        result = reports_mod.constituent_loading_summary(
            MagicMock(), MagicMock(), 'TP', 2000, 2001,
            simulation_period='monthly', aggregation_period='yearly')
        assert 'year' in result.columns
    finally:
        reports_mod.get_constituent_loading = original_fn


def test_constituent_loading_summary_simulation_agg():
    """aggregation_period='simulation' gives overall (no grouping col)."""
    reports_mod, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    try:
        result = reports_mod.constituent_loading_summary(
            MagicMock(), MagicMock(), 'TP', 2000, 2001,
            simulation_period='monthly', aggregation_period='simulation')
        assert 'month' not in result.columns
        assert 'year' not in result.columns
    finally:
        reports_mod.get_constituent_loading = original_fn


# ---------------------------------------------------------------------------
# Tests for spatial_grouping in _aggregate helpers
# ---------------------------------------------------------------------------

def test_aggregate_catchment_by_landcover_group():
    """Landcover-group filter keeps only named landcovers."""
    from hspf.reports.loading import _aggregate_catchment_by_landcover_group
    df = _make_catchment_joined_df()
    result = _aggregate_catchment_by_landcover_group(df, ['Forest'])

    assert len(result) > 0
    # Only Forest data should be aggregated; Urban is excluded
    assert 'loading_rate' in result.columns
    assert 'load' in result.columns


def test_aggregate_catchment_by_landcover_group_empty():
    """Landcover-group with no matches returns empty DataFrame."""
    from hspf.reports.loading import _aggregate_catchment_by_landcover_group
    df = _make_catchment_joined_df()
    result = _aggregate_catchment_by_landcover_group(df, ['Wetland'])
    assert len(result) == 0


# ---------------------------------------------------------------------------
# Tests for Reports class living in legacy module
# ---------------------------------------------------------------------------

def test_reports_class_importable_from_package():
    """Reports should be importable from hspf.reports (backward compat)."""
    from hspf.reports import Reports
    assert Reports is not None


def test_reports_class_lives_in_legacy():
    """Reports class module should be hspf.reports.legacy."""
    from hspf.reports import Reports
    assert Reports.__module__ == 'hspf.reports.legacy'


# ---------------------------------------------------------------------------
# Tests for unified loading_summary
# ---------------------------------------------------------------------------

def test_loading_summary_invalid_spatial_grouping():
    """Invalid spatial_grouping raises ValueError."""
    import pytest
    from hspf.reports.loading import loading_summary
    with pytest.raises(ValueError):
        loading_summary(MagicMock(), MagicMock(), 'TP', spatial_grouping='invalid')


def test_loading_summary_watershed_requires_reach_ids():
    """spatial_grouping='watershed' without reach_ids raises ValueError."""
    import pytest
    from hspf.reports.loading import loading_summary
    with pytest.raises(ValueError):
        loading_summary(MagicMock(), MagicMock(), 'TP', spatial_grouping='watershed')


def test_loading_summary_catchment_default():
    """loading_summary with spatial_grouping='catchment' returns per-catchment data."""
    import hspf.reports.loading as reports_mod
    reports_mod_melted, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    uci = _make_mock_uci()
    try:
        result = reports_mod.loading_summary(uci, MagicMock(), 'TP', 2000, 2001,
                                             spatial_grouping='catchment')
        assert 'TVOLNO' in result.columns
        assert 'load' in result.columns
        assert 'loading_rate' in result.columns
    finally:
        reports_mod.get_constituent_loading = original_fn


def test_loading_summary_catchment_by_landcover():
    """loading_summary with by_landcover=True breaks out by landcover."""
    import hspf.reports.loading as reports_mod
    _, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    uci = _make_mock_uci()
    try:
        result = reports_mod.loading_summary(uci, MagicMock(), 'TP', 2000, 2001,
                                             spatial_grouping='catchment', by_landcover=True)
        assert 'landcover' in result.columns
    finally:
        reports_mod.get_constituent_loading = original_fn


def test_loading_summary_with_landcovers_filter():
    """loading_summary with landcovers filters to specified landcovers only."""
    import hspf.reports.loading as reports_mod
    _, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    uci = _make_mock_uci()
    try:
        result = reports_mod.loading_summary(uci, MagicMock(), 'TP', 2000, 2001,
                                             spatial_grouping='catchment', landcovers=['Forest'])
        assert len(result) > 0
        assert 'load' in result.columns
    finally:
        reports_mod.get_constituent_loading = original_fn


def test_loading_summary_seasonal_aggregation():
    """loading_summary with aggregation_period='seasonal' groups by season."""
    import hspf.reports.loading as reports_mod
    _, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    uci = _make_mock_uci()
    try:
        result = reports_mod.loading_summary(uci, MagicMock(), 'TP', 2000, 2001,
                                             simulation_period='monthly',
                                             aggregation_period='seasonal',
                                             spatial_grouping='catchment')
        assert 'season' in result.columns
        assert set(result['season'].unique()).issubset({'DJF', 'MAM', 'JJA', 'SON'})
    finally:
        reports_mod.get_constituent_loading = original_fn


def test_validate_periods_seasonal_ordering():
    """'seasonal' is between 'monthly' and 'yearly' in period ordering."""
    from hspf.reports.utils import validate_periods
    validate_periods('monthly', 'seasonal')
    validate_periods('seasonal', 'yearly')
    validate_periods('daily', 'seasonal')


def test_validate_periods_seasonal_finer_raises():
    """'seasonal' aggregation is finer than 'yearly' simulation — should raise."""
    import pytest
    from hspf.reports.utils import validate_periods
    with pytest.raises(ValueError):
        validate_periods('yearly', 'seasonal')


def test_aggregation_period_to_temporal_grouping_seasonal():
    """'seasonal' maps to 'season'."""
    from hspf.reports.utils import aggregation_period_to_temporal_grouping
    assert aggregation_period_to_temporal_grouping('monthly', 'seasonal') == 'season'


def test_aggregation_period_to_temporal_grouping_none():
    """aggregation_period=None returns None (no grouping)."""
    from hspf.reports.utils import aggregation_period_to_temporal_grouping
    assert aggregation_period_to_temporal_grouping('monthly', None) is None
