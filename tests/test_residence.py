import numpy as np
import pandas as pd
import pytest

from hspf.reports.residence import (
    nominal_residence_time,
    residence_time_stats,
    turnover_ratio,
    exceedance_probability,
    cumulative_exposure,
    residence_time_distribution,
    seasonal_residence_time,
    multi_reach_residence_time,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_daily_index(n=365):
    return pd.date_range("2000-01-01", periods=n, freq="D")


def _make_hourly_index(n=24 * 30):
    return pd.date_range("2000-01-01", periods=n, freq="h")


def _make_volume_outflow(n=365, vol=100.0, out=10.0, seed=42):
    """Constant volume & outflow series (daily) with optional noise."""
    idx = _make_daily_index(n)
    rng = np.random.default_rng(seed)
    volume = pd.Series(vol + rng.normal(0, 1, n), index=idx, name="VOL")
    outflow = pd.Series(out + rng.normal(0, 0.1, n), index=idx, name="ROVOL")
    outflow = outflow.clip(lower=0.01)          # keep positive
    return volume, outflow


# ---------------------------------------------------------------------------
# Tests — nominal_residence_time
# ---------------------------------------------------------------------------

def test_residence_time_constant():
    """With constant V and Q, τ should be V/Q at every step."""
    idx = _make_daily_index(10)
    vol = pd.Series(100.0, index=idx)
    out = pd.Series(10.0, index=idx)
    rt = nominal_residence_time(vol, out)
    assert np.allclose(rt.values, 10.0)


def test_residence_time_zero_outflow_gives_nan():
    idx = _make_daily_index(5)
    vol = pd.Series(100.0, index=idx)
    out = pd.Series([10, 0, 5, 0, 10], index=idx, dtype=float)
    rt = nominal_residence_time(vol, out)
    assert np.isnan(rt.iloc[1])
    assert np.isnan(rt.iloc[3])
    assert np.isclose(rt.iloc[0], 10.0)


def test_residence_time_negative_outflow_gives_nan():
    idx = _make_daily_index(3)
    vol = pd.Series(100.0, index=idx)
    out = pd.Series([10, -5, 10], index=idx, dtype=float)
    rt = nominal_residence_time(vol, out)
    assert np.isnan(rt.iloc[1])


def test_residence_time_type_error():
    with pytest.raises(TypeError):
        nominal_residence_time([1, 2, 3], pd.Series([1, 2, 3]))


def test_residence_time_misaligned_index():
    idx_a = _make_daily_index(5)
    idx_b = pd.date_range("2001-01-01", periods=5, freq="D")
    vol = pd.Series(100.0, index=idx_a)
    out = pd.Series(10.0, index=idx_b)
    with pytest.raises(ValueError):
        nominal_residence_time(vol, out)


# ---------------------------------------------------------------------------
# Tests — residence_time_stats
# ---------------------------------------------------------------------------

def test_stats_keys():
    vol, out = _make_volume_outflow(n=100)
    stats = residence_time_stats(vol, out)
    for key in ["count", "mean", "std", "min", "max", "p10", "p50", "p90"]:
        assert key in stats.index


def test_stats_custom_percentiles():
    vol, out = _make_volume_outflow(n=100)
    stats = residence_time_stats(vol, out, percentiles=[5, 95])
    assert "p5" in stats.index
    assert "p95" in stats.index


def test_stats_mean_close_to_expected():
    """For constant V=100, Q=10, mean τ ≈ 10 days."""
    idx = _make_daily_index(200)
    vol = pd.Series(100.0, index=idx)
    out = pd.Series(10.0, index=idx)
    stats = residence_time_stats(vol, out)
    assert np.isclose(stats["mean"], 10.0)


# ---------------------------------------------------------------------------
# Tests — turnover_ratio
# ---------------------------------------------------------------------------

def test_turnover_ratio_constant():
    """With V=100, Q_out=10/day, annual turnover ≈ 365*10/100 = 36.5."""
    idx = _make_daily_index(365)
    vol = pd.Series(100.0, index=idx)
    out = pd.Series(10.0, index=idx)
    df = turnover_ratio(vol, out, freq="YE")
    assert np.isclose(df["turnover_ratio"].iloc[0], 365 * 10 / 100)


def test_turnover_ratio_monthly():
    idx = _make_daily_index(365)
    vol = pd.Series(100.0, index=idx)
    out = pd.Series(10.0, index=idx)
    df = turnover_ratio(vol, out, freq="ME")
    assert len(df) == 12  # 12 complete months in 365-day span from Jan 1


def test_turnover_ratio_columns():
    vol, out = _make_volume_outflow(n=365)
    df = turnover_ratio(vol, out)
    assert set(df.columns) == {"mean_volume", "total_outflow", "turnover_ratio"}


# ---------------------------------------------------------------------------
# Tests — exceedance_probability
# ---------------------------------------------------------------------------

def test_exceedance_probability_shape():
    vol, out = _make_volume_outflow(n=100)
    df = exceedance_probability(vol, out)
    assert len(df) > 0
    assert set(df.columns) == {"residence_time", "exceedance_probability"}


def test_exceedance_probability_bounds():
    vol, out = _make_volume_outflow(n=100)
    df = exceedance_probability(vol, out)
    assert df["exceedance_probability"].min() > 0
    assert df["exceedance_probability"].max() < 1


def test_exceedance_probability_sorted():
    vol, out = _make_volume_outflow(n=100)
    df = exceedance_probability(vol, out)
    assert (df["residence_time"].diff().dropna() <= 0).all()


def test_exceedance_probability_empty_when_no_outflow():
    idx = _make_daily_index(5)
    vol = pd.Series(100.0, index=idx)
    out = pd.Series(0.0, index=idx)
    df = exceedance_probability(vol, out)
    assert len(df) == 0


# ---------------------------------------------------------------------------
# Tests — cumulative_exposure
# ---------------------------------------------------------------------------

def test_cumulative_exposure_columns():
    vol, out = _make_volume_outflow(n=50)
    conc = pd.Series(2.0, index=vol.index)
    df = cumulative_exposure(vol, out, conc)
    assert set(df.columns) == {"residence_time", "concentration", "ct", "cumulative_ct"}


def test_cumulative_exposure_ct_product():
    idx = _make_daily_index(10)
    vol = pd.Series(100.0, index=idx)
    out = pd.Series(10.0, index=idx)
    conc = pd.Series(5.0, index=idx)
    df = cumulative_exposure(vol, out, conc)
    # τ = 10, C = 5 → C·T = 50
    assert np.allclose(df["ct"].values, 50.0)


def test_cumulative_exposure_running_sum():
    idx = _make_daily_index(5)
    vol = pd.Series(100.0, index=idx)
    out = pd.Series(10.0, index=idx)
    conc = pd.Series(1.0, index=idx)
    df = cumulative_exposure(vol, out, conc)
    # cumulative_ct at step i = (i+1) * 10
    expected = np.array([10, 20, 30, 40, 50], dtype=float)
    assert np.allclose(df["cumulative_ct"].values, expected)


# ---------------------------------------------------------------------------
# Tests — residence_time_distribution
# ---------------------------------------------------------------------------

def test_rtd_columns():
    vol, out = _make_volume_outflow(n=200)
    df = residence_time_distribution(vol, out, bins=20)
    assert set(df.columns) == {"bin_center", "frequency", "density"}


def test_rtd_frequency_sums():
    vol, out = _make_volume_outflow(n=200)
    rt = nominal_residence_time(vol, out).dropna()
    df = residence_time_distribution(vol, out, bins=20)
    assert df["frequency"].sum() == len(rt)


def test_rtd_empty():
    idx = _make_daily_index(5)
    vol = pd.Series(100.0, index=idx)
    out = pd.Series(0.0, index=idx)
    df = residence_time_distribution(vol, out)
    assert len(df) == 0


# ---------------------------------------------------------------------------
# Tests — seasonal_residence_time
# ---------------------------------------------------------------------------

def test_seasonal_month():
    vol, out = _make_volume_outflow(n=365)
    df = seasonal_residence_time(vol, out, grouping="month")
    assert df.index.name == "month"
    assert len(df) == 12


def test_seasonal_season():
    vol, out = _make_volume_outflow(n=365)
    df = seasonal_residence_time(vol, out, grouping="season")
    assert df.index.name == "season"
    assert set(df.index).issubset({"DJF", "MAM", "JJA", "SON"})


def test_seasonal_year():
    vol, out = _make_volume_outflow(n=365)
    df = seasonal_residence_time(vol, out, grouping="year")
    assert df.index.name == "year"


def test_seasonal_invalid_grouping():
    vol, out = _make_volume_outflow(n=10)
    with pytest.raises(ValueError):
        seasonal_residence_time(vol, out, grouping="invalid")


# ---------------------------------------------------------------------------
# Tests — multi_reach_residence_time
# ---------------------------------------------------------------------------

def test_multi_reach_basic():
    idx = _make_daily_index(100)
    volumes = pd.DataFrame({
        1: pd.Series(100.0, index=idx),
        2: pd.Series(200.0, index=idx),
    })
    outflows = pd.DataFrame({
        1: pd.Series(10.0, index=idx),
        2: pd.Series(50.0, index=idx),
    })
    df = multi_reach_residence_time(volumes, outflows)
    assert len(df) == 2
    assert np.isclose(df.loc[1, "mean"], 10.0)
    assert np.isclose(df.loc[2, "mean"], 4.0)


def test_multi_reach_skips_missing():
    idx = _make_daily_index(50)
    volumes = pd.DataFrame({1: pd.Series(100.0, index=idx), 3: pd.Series(50.0, index=idx)})
    outflows = pd.DataFrame({1: pd.Series(10.0, index=idx)})  # reach 3 not in outflows
    df = multi_reach_residence_time(volumes, outflows)
    assert len(df) == 1
    assert 1 in df.index


def test_multi_reach_columns():
    idx = _make_daily_index(50)
    volumes = pd.DataFrame({1: pd.Series(100.0, index=idx)})
    outflows = pd.DataFrame({1: pd.Series(10.0, index=idx)})
    df = multi_reach_residence_time(volumes, outflows)
    for col in ["mean", "median", "std", "min", "max", "count"]:
        assert col in df.columns


# ---------------------------------------------------------------------------
# Tests — hourly timestep support
# ---------------------------------------------------------------------------

def test_hourly_residence_time():
    idx = _make_hourly_index(48)
    vol = pd.Series(100.0, index=idx)
    out = pd.Series(5.0, index=idx)
    rt = nominal_residence_time(vol, out)
    # τ = 100/5 = 20 hours
    assert np.allclose(rt.values, 20.0)
