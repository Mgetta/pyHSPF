import pandas as pd
import numpy as np
from unittest.mock import MagicMock
from hspf.reports import (
    _join_catchments,
    _average_constituent_loading,
    _aggregate_catchment_loading,
    _filter_to_watershed,
    catchment_areas,
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
        data['datetime'] = pd.to_datetime(['2000-01-01', '2000-01-01', '2000-01-01', '2000-01-01'])
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

    # Mock get_constituent_loading via the function's internal call
    # Since _average_constituent_loading calls get_constituent_loading which calls hbn methods,
    # we'll test via direct invocation with a monkeypatch approach
    import hspf.reports as reports_mod

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
    import hspf.reports as reports_mod

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
