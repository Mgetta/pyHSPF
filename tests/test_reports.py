import pandas as pd
import numpy as np
import pytest
from unittest.mock import MagicMock
from hspf.reports.loading import (
    _join_catchments,
    _filter_to_watershed,
    catchment_areas,
    constituent_loading_summary,
)
from hspf.reports._analytics.timeseries import filter_years, filter_months, aggregate
from hspf.reports._analytics.loading import compute_load, compute_loading_rate


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
# Tests for _filter_to_watershed
# ---------------------------------------------------------------------------

def _make_catchment_joined_df():
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
    return pd.DataFrame(data)

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
    """Use max aggregation with simulation-level aggregation."""
    reports_mod, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    try:
        result = reports_mod.constituent_loading_summary(
            MagicMock(), MagicMock(), 'TP', 2000, 2001,
            simulation_period='monthly', aggregation_period='simulation', agg_func='max')
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


# ---------------------------------------------------------------------------
# Helpers shared by timeseries and loading analytics tests
# ---------------------------------------------------------------------------

def _make_monthly_ts(n_years=3):
    """Create a simple monthly DataFrame with DatetimeIndex spanning n_years."""
    idx = pd.date_range('2000-01-01', periods=12 * n_years, freq='MS')
    return pd.DataFrame(
        {'A': np.arange(float(12 * n_years)), 'B': np.arange(12.0 * n_years, 24.0 * n_years)},
        index=idx,
    )


# ---------------------------------------------------------------------------
# Tests for filter_years
# ---------------------------------------------------------------------------

def test_filter_years_lower_bound():
    ts = _make_monthly_ts(3)
    result = filter_years(ts, start_year=2001)
    assert result.index.year.min() == 2001


def test_filter_years_upper_bound():
    ts = _make_monthly_ts(3)
    result = filter_years(ts, end_year=2001)
    assert result.index.year.max() == 2001


def test_filter_years_closed_range():
    ts = _make_monthly_ts(3)
    result = filter_years(ts, start_year=2001, end_year=2001)
    assert len(result) == 12
    assert (result.index.year == 2001).all()


def test_filter_years_no_bounds_returns_all():
    ts = _make_monthly_ts(3)
    result = filter_years(ts)
    assert len(result) == len(ts)


def test_filter_years_preserves_series():
    ts = _make_monthly_ts(2)['A']
    result = filter_years(ts, start_year=2001)
    assert isinstance(result, pd.Series)
    assert result.index.year.min() == 2001


# ---------------------------------------------------------------------------
# Tests for filter_months
# ---------------------------------------------------------------------------

def test_filter_months_summer():
    ts = _make_monthly_ts(3)
    result = filter_months(ts, [6, 7, 8])
    assert set(result.index.month.unique()) == {6, 7, 8}
    assert len(result) == 9  # 3 years × 3 months


def test_filter_months_single():
    ts = _make_monthly_ts(3)
    result = filter_months(ts, [1])
    assert len(result) == 3  # one January per year


def test_filter_months_preserves_series():
    ts = _make_monthly_ts(2)['A']
    result = filter_months(ts, [3, 4, 5])
    assert isinstance(result, pd.Series)
    assert set(result.index.month.unique()) == {3, 4, 5}


# ---------------------------------------------------------------------------
# Tests for aggregate
# ---------------------------------------------------------------------------

def test_aggregate_by_none_returns_series():
    ts = _make_monthly_ts(3)
    result = aggregate(ts, by=None, agg_func='mean')
    assert isinstance(result, pd.Series)
    assert len(result) == 2


def test_aggregate_by_year_returns_n_years():
    ts = _make_monthly_ts(3)
    result = aggregate(ts, by='year', agg_func='sum')
    assert len(result) == 3


def test_aggregate_by_month_returns_12():
    ts = _make_monthly_ts(3)
    result = aggregate(ts, by='month', agg_func='mean')
    assert len(result) == 12


def test_aggregate_by_season_returns_4():
    ts = _make_monthly_ts(3)
    result = aggregate(ts, by='season', agg_func='sum')
    assert len(result) == 4
    assert set(result.index) == {'DJF', 'MAM', 'JJA', 'SON'}


def test_aggregate_by_year_season_shape():
    ts = _make_monthly_ts(3)
    result = aggregate(ts, by=['year', 'season'], agg_func='sum')
    assert len(result) == 12  # 3 years × 4 seasons


def test_aggregate_custom_season_map():
    ts = _make_monthly_ts(3)
    custom = {m: 'wet' if m in [11, 12, 1, 2, 3, 4] else 'dry' for m in range(1, 13)}
    result = aggregate(ts, by='season', season_map=custom)
    assert set(result.index) == {'wet', 'dry'}


def test_aggregate_invalid_key_raises():
    ts = _make_monthly_ts(3)
    with pytest.raises(ValueError, match="Unknown grouping key"):
        aggregate(ts, by='quarter')


def test_aggregate_by_string_and_list_equivalent():
    ts = _make_monthly_ts(3)
    r_str = aggregate(ts, by='year', agg_func='mean')
    r_list = aggregate(ts, by=['year'], agg_func='mean')
    pd.testing.assert_frame_equal(r_str, r_list)


# Pipeline: average of annual summer totals
def test_aggregate_pipeline_annual_summer():
    ts = _make_monthly_ts(3)
    summer = filter_months(filter_years(ts, 2000, 2002), [6, 7, 8])
    annual_summer = aggregate(summer, by='year', agg_func='sum')
    result = aggregate(annual_summer, by=None, agg_func='mean')
    assert isinstance(result, pd.Series)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Tests for compute_load and compute_loading_rate
# ---------------------------------------------------------------------------

def test_compute_load_scalar_area():
    ts = _make_monthly_ts(1)
    result = compute_load(ts, 10.0)
    pd.testing.assert_frame_equal(result, ts * 10.0)


def test_compute_loading_rate_scalar_area():
    ts = _make_monthly_ts(1)
    load = compute_load(ts, 10.0)
    result = compute_loading_rate(load, 10.0)
    pd.testing.assert_frame_equal(result, ts)


def test_compute_load_series_area():
    ts = _make_monthly_ts(1)
    area = pd.Series({'A': 5.0, 'B': 20.0})
    result = compute_load(ts, area)
    assert np.allclose(result['A'], ts['A'] * 5.0)
    assert np.allclose(result['B'], ts['B'] * 20.0)


def test_compute_loading_rate_series_area():
    ts = _make_monthly_ts(1)
    area = pd.Series({'A': 5.0, 'B': 20.0})
    load = compute_load(ts, area)
    result = compute_loading_rate(load, area)
    pd.testing.assert_frame_equal(result, ts)
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
    """'seasonal' aggregation is finer than 'yearly' simulation - should raise."""
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


def test_constituent_loading_summary_equal_periods_groups():
    """simulation_period='monthly', aggregation_period='monthly' groups by month."""
    reports_mod, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    try:
        result = reports_mod.constituent_loading_summary(
            MagicMock(), MagicMock(), 'TP', 2000, 2001,
            simulation_period='monthly', aggregation_period='monthly')
        assert 'month' in result.columns
    finally:
        reports_mod.get_constituent_loading = original_fn


# ---------------------------------------------------------------------------
# Tests for _analytics.yields (model-agnostic layer)
# ---------------------------------------------------------------------------

def _make_load_series():
    """Monthly load timeseries spanning 2000-2002 (36 months)."""
    dates = pd.date_range('2000-01-01', periods=36, freq='MS')
    return pd.Series(np.arange(1.0, 37.0), index=dates)


def _make_load_dataframe():
    """Monthly load DataFrame with two reaches spanning 2000-2002."""
    dates = pd.date_range('2000-01-01', periods=36, freq='MS')
    return pd.DataFrame({'R1': np.arange(1.0, 37.0),
                         'R2': np.arange(37.0, 73.0)}, index=dates)


def test_compute_yield_scalar_area():
    from hspf.reports._analytics.yields import compute_yield
    load = _make_load_series()
    yld = compute_yield(load, 100.0)
    assert np.allclose(yld, load / 100.0)


def test_compute_yield_series_area():
    from hspf.reports._analytics.yields import compute_yield
    load = _make_load_dataframe()
    areas = pd.Series({'R1': 100.0, 'R2': 200.0})
    yld = compute_yield(load, areas)
    assert np.allclose(yld['R1'], load['R1'] / 100.0)
    assert np.allclose(yld['R2'], load['R2'] / 200.0)


def test_compute_net_load_no_upstream():
    from hspf.reports._analytics.yields import compute_net_load
    load = _make_load_series()
    net = compute_net_load(load)
    assert (net == load).all()


def test_compute_net_load_with_upstream():
    from hspf.reports._analytics.yields import compute_net_load
    load = _make_load_series()
    upstream = load * 0.4
    net = compute_net_load(load, upstream)
    assert np.allclose(net, load - upstream)


def test_average_annual_full_range():
    from hspf.reports._analytics.yields import average_annual
    load = _make_load_series()
    result = average_annual(load)
    assert np.isclose(result, load.mean())


def test_average_annual_filtered():
    from hspf.reports._analytics.yields import average_annual
    load = _make_load_series()
    result = average_annual(load, start_year=2000, end_year=2000)
    assert np.isclose(result, load['2000'].mean())


def test_average_monthly_returns_12_months():
    from hspf.reports._analytics.yields import average_monthly
    load = _make_load_series()
    result = average_monthly(load)
    assert len(result) == 12
    assert list(result.index) == list(range(1, 13))


def test_average_monthly_filtered():
    from hspf.reports._analytics.yields import average_monthly
    load = _make_load_series()
    result = average_monthly(load, start_year=2000, end_year=2000)
    assert len(result) == 12


def test_annual_totals():
    from hspf.reports._analytics.yields import annual_totals
    load = _make_load_series()
    result = annual_totals(load, 2000, 2001)
    assert len(result) == 2
    assert set(result.index) == {2000, 2001}
    assert np.isclose(result[2000], load['2000'].sum())


def test_monthly_totals():
    from hspf.reports._analytics.yields import monthly_totals
    load = _make_load_series()
    result = monthly_totals(load, 2000, 2001)
    assert len(result) == 24  # 12 months × 2 years


def test_yield_summary_keys():
    from hspf.reports._analytics.yields import yield_summary
    load = _make_load_series()
    result = yield_summary(load, 500.0, 2000, 2001)
    assert set(result.keys()) == {'timeseries', 'annual_average', 'monthly_average'}


def test_yield_summary_timeseries_shape():
    from hspf.reports._analytics.yields import yield_summary
    load = _make_load_series()
    result = yield_summary(load, 500.0)
    assert len(result['timeseries']) == len(load)
    assert np.allclose(result['timeseries'], load / 500.0)


def test_yield_summary_monthly_average_length():
    from hspf.reports._analytics.yields import yield_summary
    load = _make_load_series()
    result = yield_summary(load, 500.0)
    assert len(result['monthly_average']) == 12


def test_analytics_exports_from_package():
    """Analytics functions are accessible from the top-level reports package."""
    from hspf.reports import (
        compute_yield, compute_net_load, average_annual,
        average_monthly, annual_totals, monthly_totals, yield_summary,
    )
    assert callable(compute_yield)
    assert callable(yield_summary)
