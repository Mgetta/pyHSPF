import numpy as np
import pandas as pd
import pytest

from hspf.reports import independent_peaks


def two_crest_series():
    index = pd.date_range('2020-01-01', periods=18, freq='D')
    values = [1, 2, 4, 8, 12, 10, 9, 8.5, 8, 8.5, 9, 10, 8, 6, 4, 3, 2, 1]
    return pd.Series(values, index=index)


def test_independent_peaks_applies_trough_rule():
    series = two_crest_series()

    peaks = independent_peaks(series, n=2, min_separation_days=5)
    relaxed = independent_peaks(
        series, n=2, min_separation_days=5, trough_ratio=0.85)

    assert peaks['datetime'].tolist() == [pd.Timestamp('2020-01-05')]
    assert relaxed['datetime'].tolist() == [
        pd.Timestamp('2020-01-05'), pd.Timestamp('2020-01-12')]


def test_independent_peaks_area_sets_uswrc_separation():
    series = two_crest_series()

    peaks = independent_peaks(
        series, n=2, drainage_area_sqmi=1375, trough_ratio=0.85)

    assert peaks['datetime'].tolist() == [pd.Timestamp('2020-01-05')]


def test_independent_peaks_returns_ranked_event_context():
    peaks = independent_peaks(
        two_crest_series(), n=2, min_separation_days=5, trough_ratio=0.85)

    assert peaks.columns.tolist() == [
        'rank', 'datetime', 'value', 'event_start', 'event_end',
        'trough_before', 'trough_after', 'days_to_prev_event']
    assert peaks['rank'].tolist() == [1, 2]
    assert peaks.loc[0, 'event_start'] < peaks.loc[0, 'datetime']
    assert peaks.loc[0, 'event_end'] > peaks.loc[0, 'datetime']
    assert np.isnan(peaks.loc[0, 'days_to_prev_event'])


def test_independent_peaks_uses_larger_value_on_peak_plateau():
    index = pd.date_range('2020-01-01', periods=7, freq='D')
    series = pd.Series([1, 3, 5, 5, 4, 2, 1], index=index)

    peaks = independent_peaks(series)

    assert peaks['datetime'].tolist() == [pd.Timestamp('2020-01-03')]


def test_independent_peaks_validates_inputs():
    series = two_crest_series()

    with pytest.raises(ValueError, match='cunnane requires'):
        independent_peaks(series, method='cunnane')
    with pytest.raises(ValueError, match='positive'):
        independent_peaks(series, drainage_area_sqmi=0)
    with pytest.raises(TypeError, match='DatetimeIndex'):
        independent_peaks(pd.Series([1, 2, 1]))
