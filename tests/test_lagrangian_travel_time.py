# -*- coding: utf-8 -*-
"""Unit tests for the Section 6 Lagrangian Travel Time functions in residence.py."""
import math
import numpy as np
import pandas as pd
import pytest

from hspf.reports.residence import (
    _interpolate_tau,
    lagrangian_travel_time,
    lagrangian_travel_times,
    lagrangian_travel_time_summary,
    lagrangian_travel_time_exceedance,
    compare_lagrangian_vs_dynamic,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tau_df(n_times=10, dt_hours=1.0, reaches=(1, 2, 3), tau_value=2.0):
    """Return a constant-tau DataFrame (reaches x timesteps)."""
    idx = pd.date_range('2020-01-01', periods=n_times, freq='h')
    return pd.DataFrame(tau_value, index=idx, columns=list(reaches))


def _make_reach_frames(n_times=10, dt_hours=1.0, reaches=(1, 2, 3),
                       vol_acft=10.0, outflow_cfs=50.0):
    """Return reach_volumes and reach_outflows DataFrames."""
    idx = pd.date_range('2020-01-01', periods=n_times, freq='h')
    volumes = pd.DataFrame(vol_acft, index=idx, columns=list(reaches))
    outflows = pd.DataFrame(outflow_cfs, index=idx, columns=list(reaches))
    return volumes, outflows


# ---------------------------------------------------------------------------
# Tests for _interpolate_tau
# ---------------------------------------------------------------------------

class TestInterpolateTau:

    def test_exact_integer_boundary_first(self):
        """Exact integer boundary at index 0 returns tau_lo directly."""
        tau_df = _make_tau_df(n_times=5, tau_value=3.0)
        result = _interpolate_tau(tau_df, 1, 0.0, 0.0, 1.0)
        assert result == pytest.approx(3.0)

    def test_exact_integer_boundary_mid(self):
        """Exact integer boundary at a middle index returns that value."""
        tau_df = _make_tau_df(n_times=10, tau_value=2.0)
        result = _interpolate_tau(tau_df, 1, 3.0, 0.0, 1.0)
        assert result == pytest.approx(2.0)

    def test_fractional_interpolation(self):
        """Fractional arrival interpolates linearly between the two brackets."""
        idx = pd.date_range('2020-01-01', periods=5, freq='h')
        tau_df = pd.DataFrame({'A': [2.0, 4.0, 6.0, 8.0, 10.0]}, index=idx)
        # arrival_hours=1.5 → idx_float=1.5 → lo=1 (tau=4), hi=2 (tau=6)
        # interp = 4 + (6-4)*0.5 = 5.0
        result = _interpolate_tau(tau_df, 'A', 1.5, 0.0, 1.0)
        assert result == pytest.approx(5.0)

    def test_negative_idx_returns_nan(self):
        """Arrival before the start of the timeseries returns NaN."""
        tau_df = _make_tau_df(n_times=5)
        result = _interpolate_tau(tau_df, 1, -1.0, 0.0, 1.0)
        assert math.isnan(result)

    def test_beyond_end_fractional_returns_nan(self):
        """Arrival that requires idx_hi beyond the end returns NaN."""
        tau_df = _make_tau_df(n_times=5, tau_value=3.0)
        # arrival_hours=4.5 → idx_lo=4 (last valid), idx_hi=5 (out of bounds), frac=0.5
        result = _interpolate_tau(tau_df, 1, 4.5, 0.0, 1.0)
        assert math.isnan(result)

    def test_exact_last_index_returns_value(self):
        """Exact arrival at the last index (frac=0) returns tau_lo, not NaN."""
        tau_df = _make_tau_df(n_times=5, tau_value=3.0)
        result = _interpolate_tau(tau_df, 1, 4.0, 0.0, 1.0)
        assert result == pytest.approx(3.0)

    def test_nan_tau_lo_returns_nan(self):
        """NaN at the lower bracket propagates to NaN."""
        idx = pd.date_range('2020-01-01', periods=5, freq='h')
        tau_df = pd.DataFrame({'A': [np.nan, 2.0, 2.0, 2.0, 2.0]}, index=idx)
        result = _interpolate_tau(tau_df, 'A', 0.3, 0.0, 1.0)
        assert math.isnan(result)

    def test_nan_tau_hi_returns_nan(self):
        """NaN at the upper bracket propagates to NaN."""
        idx = pd.date_range('2020-01-01', periods=5, freq='h')
        tau_df = pd.DataFrame({'A': [2.0, np.nan, 2.0, 2.0, 2.0]}, index=idx)
        result = _interpolate_tau(tau_df, 'A', 0.3, 0.0, 1.0)
        assert math.isnan(result)

    def test_t0_epoch_offset_applied(self):
        """Non-zero t0_epoch_hours shifts the arrival time correctly."""
        tau_df = _make_tau_df(n_times=5, tau_value=3.0)
        # arrival_hours=2.0, t0_epoch=1.0 → relative=1.0 → idx_float=1.0 → tau_lo at idx 1
        result = _interpolate_tau(tau_df, 1, 2.0, 1.0, 1.0)
        assert result == pytest.approx(3.0)

    def test_idx_lo_at_end_exact_returns_value(self):
        """idx_lo equals last valid index with frac=0 returns that value."""
        tau_df = _make_tau_df(n_times=3, tau_value=5.0)
        result = _interpolate_tau(tau_df, 1, 2.0, 0.0, 1.0)
        assert result == pytest.approx(5.0)

    def test_idx_lo_out_of_bounds_returns_nan(self):
        """idx_lo >= n (arrival after end) returns NaN."""
        tau_df = _make_tau_df(n_times=3, tau_value=5.0)
        result = _interpolate_tau(tau_df, 1, 10.0, 0.0, 1.0)
        assert math.isnan(result)


# ---------------------------------------------------------------------------
# Tests for lagrangian_travel_time
# ---------------------------------------------------------------------------

class TestLagrangianTravelTime:

    def test_single_reach_constant_tau(self):
        """Single-reach path returns tau at the release timestep."""
        tau_df = _make_tau_df(n_times=20, tau_value=3.0, reaches=[1])
        result = lagrangian_travel_time(tau_df, [1], release_idx=0, dt_hours=1.0)
        assert result == pytest.approx(3.0)

    def test_multi_reach_constant_tau(self):
        """Multi-reach path with constant τ returns sum of taus."""
        tau_df = _make_tau_df(n_times=50, tau_value=2.0, reaches=[1, 2, 3])
        result = lagrangian_travel_time(tau_df, [1, 2, 3], release_idx=0, dt_hours=1.0)
        assert result == pytest.approx(6.0)

    def test_parcel_off_end_returns_nan(self):
        """Parcel that exceeds the timeseries returns NaN."""
        tau_df = _make_tau_df(n_times=5, tau_value=3.0, reaches=[1, 2])
        # release at idx=4 (last), tau[1]=3 → arrive at 4+3=7, beyond 5
        result = lagrangian_travel_time(tau_df, [1, 2], release_idx=4, dt_hours=1.0)
        assert math.isnan(result)

    def test_unknown_reach_returns_nan(self):
        """Reach not present in tau_df returns NaN."""
        tau_df = _make_tau_df(n_times=10, tau_value=2.0, reaches=[1])
        result = lagrangian_travel_time(tau_df, [99], release_idx=0, dt_hours=1.0)
        assert math.isnan(result)

    def test_lag_advances_clock(self):
        """Time-lagging: the second reach is evaluated at the arrival time."""
        idx = pd.date_range('2020-01-01', periods=20, freq='h')
        # Reach 1 always has tau=2.0, reach 2 has tau=1.0 for t<5, 10.0 for t>=5
        tau_r1 = [2.0] * 20
        tau_r2 = [1.0 if i < 5 else 10.0 for i in range(20)]
        tau_df = pd.DataFrame({'R1': tau_r1, 'R2': tau_r2}, index=idx)
        # Release at idx=0: R1 tau=2.0, arrive at R2 at idx=2.0 → tau_r2[2]=1.0
        # total = 2.0 + 1.0 = 3.0
        result = lagrangian_travel_time(tau_df, ['R1', 'R2'], release_idx=0, dt_hours=1.0)
        assert result == pytest.approx(3.0)

    def test_empty_path_returns_zero(self):
        """Empty path means no reaches; elapsed stays 0."""
        tau_df = _make_tau_df(n_times=10, tau_value=2.0, reaches=[1])
        result = lagrangian_travel_time(tau_df, [], release_idx=0, dt_hours=1.0)
        assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Tests for lagrangian_travel_times (bulk)
# ---------------------------------------------------------------------------

class TestLagrangianTravelTimes:

    def test_shape_matches_input(self):
        """Output DataFrame has same index as tau_df and columns=source_reach_ids."""
        volumes, outflows = _make_reach_frames(n_times=20)
        routing_paths = {1: [1, 2, 3]}
        result = lagrangian_travel_times(volumes, outflows, routing_paths)
        assert result.shape[0] == 20
        assert list(result.columns) == [1]

    def test_steady_state_matches_dynamic(self):
        """Under constant conditions, Lagrangian and dynamic methods agree."""
        volumes, outflows = _make_reach_frames(n_times=50)
        routing_paths = {1: [1, 2, 3], 2: [2, 3], 3: [3]}

        from hspf.reports.residence import dynamic_travel_times
        lag_tt = lagrangian_travel_times(volumes, outflows, routing_paths)
        dyn_tt = dynamic_travel_times(volumes, outflows, routing_paths)

        # All values should be the same (no temporal variation → no lag effect)
        for col in routing_paths:
            lag_valid = lag_tt[col].dropna()
            dyn_valid = dyn_tt[col].dropna()
            assert len(lag_valid) > 0, f"No valid values for source {col}"
            np.testing.assert_allclose(
                lag_valid.values, dyn_valid.loc[lag_valid.index].values,
                rtol=1e-6, err_msg=f"Mismatch for source reach {col}"
            )

    def test_multiple_sources(self):
        """Multiple source reaches all appear as columns."""
        volumes, outflows = _make_reach_frames(n_times=20)
        routing_paths = {1: [1, 2, 3], 2: [2, 3]}
        result = lagrangian_travel_times(volumes, outflows, routing_paths)
        assert set(result.columns) == {1, 2}

    def test_late_release_produces_nan(self):
        """A parcel released near the end that cannot complete the path is NaN."""
        volumes, outflows = _make_reach_frames(n_times=5, vol_acft=100.0,
                                               outflow_cfs=1.0)
        routing_paths = {1: [1, 2, 3]}
        result = lagrangian_travel_times(volumes, outflows, routing_paths)
        # Large tau means most or all timesteps will produce NaN
        assert result[1].isna().any()


# ---------------------------------------------------------------------------
# Tests for lagrangian_travel_time_summary
# ---------------------------------------------------------------------------

class TestLagrangianTravelTimeSummary:

    def test_output_columns(self):
        """Summary has the expected column set."""
        volumes, outflows = _make_reach_frames(n_times=30)
        routing_paths = {1: [1, 2]}
        result = lagrangian_travel_time_summary(volumes, outflows, routing_paths)
        expected_cols = {
            'mean_travel_time_hours', 'median_travel_time_hours',
            'std_travel_time_hours', 'min_travel_time_hours',
            'max_travel_time_hours', 'catchment_area_acres',
        }
        assert expected_cols == set(result.columns)

    def test_index_is_source_reach_id(self):
        """Index name is 'source_reach_id'."""
        volumes, outflows = _make_reach_frames(n_times=30)
        routing_paths = {1: [1, 2]}
        result = lagrangian_travel_time_summary(volumes, outflows, routing_paths)
        assert result.index.name == 'source_reach_id'

    def test_catchment_area_attached(self):
        """Catchment area is attached when provided."""
        volumes, outflows = _make_reach_frames(n_times=30)
        routing_paths = {1: [1, 2]}
        areas = pd.Series({1: 500.0, 2: 300.0})
        result = lagrangian_travel_time_summary(
            volumes, outflows, routing_paths, catchment_areas=areas
        )
        assert result.loc[1, 'catchment_area_acres'] == pytest.approx(500.0)

    def test_catchment_area_nan_when_absent(self):
        """Missing catchment area results in NaN."""
        volumes, outflows = _make_reach_frames(n_times=30)
        routing_paths = {1: [1, 2]}
        result = lagrangian_travel_time_summary(volumes, outflows, routing_paths)
        assert math.isnan(result.loc[1, 'catchment_area_acres'])

    def test_constant_tau_summary_stats(self):
        """Under constant tau, mean == median == min == max."""
        volumes, outflows = _make_reach_frames(n_times=50)
        routing_paths = {1: [1]}
        result = lagrangian_travel_time_summary(volumes, outflows, routing_paths)
        row = result.loc[1]
        assert row['mean_travel_time_hours'] == pytest.approx(
            row['median_travel_time_hours'], rel=1e-6
        )
        assert row['min_travel_time_hours'] == pytest.approx(
            row['max_travel_time_hours'], rel=1e-6
        )


# ---------------------------------------------------------------------------
# Tests for lagrangian_travel_time_exceedance
# ---------------------------------------------------------------------------

class TestLagrangianTravelTimeExceedance:

    def test_output_columns_default_thresholds(self):
        """Default thresholds [6, 12, 24, 48, 72, 168] are columns."""
        volumes, outflows = _make_reach_frames(n_times=50)
        routing_paths = {1: [1, 2]}
        result = lagrangian_travel_time_exceedance(volumes, outflows, routing_paths)
        assert set(result.columns) == {6, 12, 24, 48, 72, 168}

    def test_custom_thresholds(self):
        """Custom thresholds appear as columns."""
        volumes, outflows = _make_reach_frames(n_times=50)
        routing_paths = {1: [1]}
        result = lagrangian_travel_time_exceedance(
            volumes, outflows, routing_paths, thresholds_hours=[1, 2, 3]
        )
        assert set(result.columns) == {1, 2, 3}

    def test_zero_exceedance_when_tt_below_threshold(self):
        """All travel times below threshold → exceedance fraction = 0."""
        volumes, outflows = _make_reach_frames(
            n_times=50, vol_acft=1.0, outflow_cfs=10000.0
        )
        routing_paths = {1: [1]}
        result = lagrangian_travel_time_exceedance(
            volumes, outflows, routing_paths, thresholds_hours=[1000]
        )
        # Travel time is tiny, so zero should exceed 1000 hours
        assert result.loc[1, 1000] == pytest.approx(0.0)

    def test_index_is_source_reach_id(self):
        """Index name is 'source_reach_id'."""
        volumes, outflows = _make_reach_frames(n_times=50)
        routing_paths = {1: [1]}
        result = lagrangian_travel_time_exceedance(volumes, outflows, routing_paths)
        assert result.index.name == 'source_reach_id'


# ---------------------------------------------------------------------------
# Tests for compare_lagrangian_vs_dynamic
# ---------------------------------------------------------------------------

class TestCompareLagrangianVsDynamic:

    def test_output_columns(self):
        """Output has the four expected comparison columns."""
        volumes, outflows = _make_reach_frames(n_times=30)
        routing_paths = {1: [1, 2]}
        result = compare_lagrangian_vs_dynamic(volumes, outflows, routing_paths)
        assert set(result.columns) == {
            'dynamic_mean_hours', 'lagrangian_mean_hours',
            'mean_difference_hours', 'mean_ratio',
        }

    def test_steady_state_difference_zero(self):
        """Under constant conditions the difference should be ~0."""
        volumes, outflows = _make_reach_frames(n_times=50)
        routing_paths = {1: [1, 2]}
        result = compare_lagrangian_vs_dynamic(volumes, outflows, routing_paths)
        assert result.loc[1, 'mean_difference_hours'] == pytest.approx(0.0, abs=1e-9)

    def test_steady_state_ratio_one(self):
        """Under constant conditions the ratio should be ~1."""
        volumes, outflows = _make_reach_frames(n_times=50)
        routing_paths = {1: [1, 2]}
        result = compare_lagrangian_vs_dynamic(volumes, outflows, routing_paths)
        assert result.loc[1, 'mean_ratio'] == pytest.approx(1.0, rel=1e-6)

    def test_index_is_source_reach_id(self):
        """Index name is 'source_reach_id'."""
        volumes, outflows = _make_reach_frames(n_times=30)
        routing_paths = {1: [1]}
        result = compare_lagrangian_vs_dynamic(volumes, outflows, routing_paths)
        assert result.index.name == 'source_reach_id'
