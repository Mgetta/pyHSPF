import pandas as pd
import numpy as np
import pytest
from unittest.mock import MagicMock
from hspf.reports.loading import (
    _join_catchments,
    _average_constituent_loading,
    _aggregate_catchment_loading,
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
        result = reports_mod._average_constituent_loading(uci, hbn, 'TP', 2000, 2001, time_step=5)
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
        result = reports_mod._average_constituent_loading(uci, hbn, 'TP', 2000, 2001, time_step=4, group_by_month=True)
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
    """Group by year."""
    reports_mod, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    try:
        result = reports_mod.constituent_loading_summary(
            MagicMock(), MagicMock(), 'TP', 2000, 2001, temporal_grouping='year')
        assert 'year' in result.columns
        assert set(result['year'].unique()) == {2000, 2001}
    finally:
        reports_mod.get_constituent_loading = original_fn


def test_constituent_loading_summary_by_season():
    """Group by season."""
    reports_mod, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    try:
        result = reports_mod.constituent_loading_summary(
            MagicMock(), MagicMock(), 'TP', 2000, 2001, temporal_grouping='season')
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


def test_constituent_loading_summary_invalid_grouping():
    """Invalid temporal_grouping raises ValueError."""
    reports_mod, melted = _mock_get_constituent_loading()
    original_fn = reports_mod.get_constituent_loading
    reports_mod.get_constituent_loading = lambda uci, hbn, constituent, time_step: melted
    try:
        import pytest
        with pytest.raises(ValueError):
            reports_mod.constituent_loading_summary(
                MagicMock(), MagicMock(), 'TP', 2000, 2001, temporal_grouping='invalid')
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
