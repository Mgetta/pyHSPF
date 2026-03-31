"""Tests for Section 5 Lagrangian travel-time functions in residence.py."""
import importlib.util
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Load residence module directly to avoid broken __init__ imports
# ---------------------------------------------------------------------------

_RESIDENCE_PATH = Path(__file__).parent.parent / 'src' / 'hspf' / 'reports' / 'residence.py'


def _load_residence():
    """Load residence.py directly, mocking hspf.parser.graph dependency."""
    for mod_name in ['hspf', 'hspf.parser', 'hspf.parser.graph', 'hspf.reports']:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)
    spec = importlib.util.spec_from_file_location('hspf.reports.residence', str(_RESIDENCE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_res = _load_residence()

_interpolate_tau = _res._interpolate_tau
lagrangian_travel_time = _res.lagrangian_travel_time
lagrangian_travel_times = _res.lagrangian_travel_times
lagrangian_travel_time_summary = _res.lagrangian_travel_time_summary
lagrangian_travel_time_exceedance = _res.lagrangian_travel_time_exceedance
compare_lagrangian_vs_dynamic = _res.compare_lagrangian_vs_dynamic


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def steady_state():
    """10-step hourly timeseries with constant tau: R1=2h, R2=3h, R3=1h."""
    idx = pd.date_range('2000-01-01', periods=10, freq='h')
    # tau = VOL_ft3 / Q / 3600  =>  VOL_acft = tau * Q * 3600 / 43560
    acft = lambda tau_h: tau_h * 1.0 * 3600.0 / 43560.0
    vol = pd.DataFrame({'R1': acft(2.0), 'R2': acft(3.0), 'R3': acft(1.0)}, index=idx)
    q = pd.DataFrame({'R1': 1.0, 'R2': 1.0, 'R3': 1.0}, index=idx)
    paths = {'R1': ['R1', 'R2', 'R3'], 'R2': ['R2', 'R3']}
    return vol, q, paths


@pytest.fixture
def varying_tau():
    """20-step hourly timeseries with a storm event causing tau to change."""
    idx = pd.date_range('2000-01-01', periods=20, freq='h')
    # R1: tau=2h base, drops to 1h during storm (t=5..9)
    r1 = [2.0] * 5 + [1.0] * 5 + [2.0] * 10
    # R2: tau=3h base, drops to 1.5h slightly later (t=6..10)
    r2 = [3.0] * 6 + [1.5] * 5 + [3.0] * 9
    acft = lambda tau_series: [t * 1.0 * 3600.0 / 43560.0 for t in tau_series]
    vol = pd.DataFrame({'R1': acft(r1), 'R2': acft(r2)}, index=idx)
    q = pd.DataFrame({'R1': 1.0, 'R2': 1.0}, index=idx)
    paths = {'R1': ['R1', 'R2']}
    return vol, q, paths


# ---------------------------------------------------------------------------
# _interpolate_tau
# ---------------------------------------------------------------------------

class TestInterpolateTau:
    def _make_tau_df(self):
        idx = pd.date_range('2000-01-01', periods=6, freq='h')
        return pd.DataFrame({'R1': [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]}, index=idx)

    def test_exact_integer_index(self):
        tau_df = self._make_tau_df()
        assert _interpolate_tau(tau_df, 'R1', 0.0, 0.0, 1.0) == pytest.approx(1.0)
        assert _interpolate_tau(tau_df, 'R1', 2.0, 0.0, 1.0) == pytest.approx(3.0)

    def test_midpoint_interpolation(self):
        tau_df = self._make_tau_df()
        # Between idx 0 (1.0) and idx 1 (2.0), midpoint should be 1.5
        assert _interpolate_tau(tau_df, 'R1', 0.5, 0.0, 1.0) == pytest.approx(1.5)

    def test_fractional_interpolation(self):
        tau_df = self._make_tau_df()
        # At 0.25: 1.0 + 0.25 * (2.0 - 1.0) = 1.25
        assert _interpolate_tau(tau_df, 'R1', 0.25, 0.0, 1.0) == pytest.approx(1.25)

    def test_negative_arrival_returns_nan(self):
        tau_df = self._make_tau_df()
        assert np.isnan(_interpolate_tau(tau_df, 'R1', -1.0, 0.0, 1.0))

    def test_out_of_bounds_returns_nan(self):
        tau_df = self._make_tau_df()
        assert np.isnan(_interpolate_tau(tau_df, 'R1', 100.0, 0.0, 1.0))

    def test_missing_reach_returns_nan(self):
        tau_df = self._make_tau_df()
        assert np.isnan(_interpolate_tau(tau_df, 'MISSING', 0.0, 0.0, 1.0))

    def test_nan_in_tau_propagates(self):
        idx = pd.date_range('2000-01-01', periods=4, freq='h')
        tau_df = pd.DataFrame({'R1': [1.0, np.nan, 3.0, 4.0]}, index=idx)
        # Interpolating between 0 (1.0) and 1 (NaN) should return NaN
        assert np.isnan(_interpolate_tau(tau_df, 'R1', 0.5, 0.0, 1.0))

    def test_at_last_index_returns_value(self):
        tau_df = self._make_tau_df()
        # idx_lo = 5, idx_hi = 6 >= n=6 -> boundary value
        assert _interpolate_tau(tau_df, 'R1', 5.0, 0.0, 1.0) == pytest.approx(6.0)


# ---------------------------------------------------------------------------
# lagrangian_travel_time
# ---------------------------------------------------------------------------

class TestLagrangianTravelTime:
    def test_single_reach_path(self):
        idx = pd.date_range('2000-01-01', periods=10, freq='h')
        tau_df = pd.DataFrame({'R1': [2.0] * 10}, index=idx)
        tt = lagrangian_travel_time(tau_df, ['R1'], 0, 1.0)
        assert tt == pytest.approx(2.0)

    def test_three_reach_steady_state(self):
        idx = pd.date_range('2000-01-01', periods=10, freq='h')
        tau_df = pd.DataFrame({'R1': 2.0, 'R2': 3.0, 'R3': 1.0}, index=idx)
        tt = lagrangian_travel_time(tau_df, ['R1', 'R2', 'R3'], 0, 1.0)
        assert tt == pytest.approx(6.0)

    def test_returns_nan_when_packet_runs_off_end(self):
        idx = pd.date_range('2000-01-01', periods=5, freq='h')
        tau_df = pd.DataFrame({'R1': 2.0, 'R2': 3.0}, index=idx)
        # Release at idx=3: R1 tau=2 -> arrives at R2 at t=5 which is >= n=5
        tt = lagrangian_travel_time(tau_df, ['R1', 'R2'], 3, 1.0)
        assert np.isnan(tt)

    def test_empty_path_returns_zero(self):
        idx = pd.date_range('2000-01-01', periods=5, freq='h')
        tau_df = pd.DataFrame({'R1': 2.0}, index=idx)
        tt = lagrangian_travel_time(tau_df, [], 0, 1.0)
        assert tt == pytest.approx(0.0)

    def test_varying_tau_uses_arrival_time(self):
        """Parcel released at t=5 uses storm tau for R1, then arrives at R2 during storm."""
        idx = pd.date_range('2000-01-01', periods=20, freq='h')
        r1 = [2.0] * 5 + [1.0] * 5 + [2.0] * 10
        r2 = [3.0] * 6 + [1.5] * 5 + [3.0] * 9
        tau_df = pd.DataFrame({'R1': r1, 'R2': r2}, index=idx)

        tt_lag = lagrangian_travel_time(tau_df, ['R1', 'R2'], 5, 1.0)
        # R1 tau at t=5 is 1.0; arrives at R2 at t=6 where tau=1.5; total=2.5
        assert tt_lag == pytest.approx(2.5)

        # Dynamic (same-timestep) would give R1(5) + R2(5) = 1.0 + 3.0 = 4.0
        dyn_tt = r1[5] + r2[5]
        assert dyn_tt == pytest.approx(4.0)

        # Confirm Lagrangian != Dynamic when conditions vary
        assert tt_lag != pytest.approx(dyn_tt)


# ---------------------------------------------------------------------------
# lagrangian_travel_times
# ---------------------------------------------------------------------------

class TestLagrangianTravelTimes:
    def test_steady_state_equals_dynamic(self, steady_state):
        vol, q, paths = steady_state
        lag_df = lagrangian_travel_times(vol, q, paths)
        dyn_df = _res.dynamic_travel_times(vol, q, paths)

        # Under constant conditions, every valid Lagrangian value must equal
        # the corresponding dynamic value.  The Lagrangian approach may
        # return NaN for late releases where the parcel would run off the end
        # of the timeseries; the dynamic approach does not have that
        # constraint.  We compare only the timesteps where both are valid.
        for src in paths:
            valid_mask = lag_df[src].notna() & dyn_df[src].notna()
            assert valid_mask.any(), f"No overlapping valid values for {src}"
            np.testing.assert_allclose(
                lag_df[src][valid_mask].values,
                dyn_df[src][valid_mask].values,
                rtol=1e-9,
            )

    def test_output_shape(self, steady_state):
        vol, q, paths = steady_state
        result = lagrangian_travel_times(vol, q, paths)
        assert result.shape == (len(vol), len(paths))
        assert set(result.columns) == set(paths.keys())

    def test_output_index_matches_input(self, steady_state):
        vol, q, paths = steady_state
        result = lagrangian_travel_times(vol, q, paths)
        pd.testing.assert_index_equal(result.index, vol.index)

    def test_nan_for_late_releases(self):
        """Parcels released near the end should return NaN if they run off."""
        idx = pd.date_range('2000-01-01', periods=5, freq='h')
        acft = lambda tau_h: tau_h * 1.0 * 3600.0 / 43560.0
        vol = pd.DataFrame({'R1': acft(2.0), 'R2': acft(3.0)}, index=idx)
        q = pd.DataFrame({'R1': 1.0, 'R2': 1.0}, index=idx)
        paths = {'R1': ['R1', 'R2']}
        result = lagrangian_travel_times(vol, q, paths)
        # Total tau = 5h; any release at t >= 1 will run off the 5-step series
        assert np.isnan(result['R1'].iloc[-1])


# ---------------------------------------------------------------------------
# lagrangian_travel_time_summary
# ---------------------------------------------------------------------------

class TestLagrangianTravelTimeSummary:
    def test_columns(self, steady_state):
        vol, q, paths = steady_state
        summary = lagrangian_travel_time_summary(vol, q, paths)
        expected_cols = {
            'mean_travel_time_hours', 'median_travel_time_hours',
            'std_travel_time_hours', 'min_travel_time_hours',
            'max_travel_time_hours', 'catchment_area_acres',
        }
        assert set(summary.columns) == expected_cols

    def test_index_name(self, steady_state):
        vol, q, paths = steady_state
        summary = lagrangian_travel_time_summary(vol, q, paths)
        assert summary.index.name == 'source_reach_id'

    def test_catchment_areas_attached(self, steady_state):
        vol, q, paths = steady_state
        areas = pd.Series({'R1': 100.0, 'R2': 50.0})
        summary = lagrangian_travel_time_summary(vol, q, paths, catchment_areas=areas)
        assert summary.loc['R1', 'catchment_area_acres'] == pytest.approx(100.0)
        assert summary.loc['R2', 'catchment_area_acres'] == pytest.approx(50.0)

    def test_steady_state_stats(self, steady_state):
        """Under constant tau, mean==median==min==max and std==0."""
        vol, q, paths = steady_state
        summary = lagrangian_travel_time_summary(vol, q, paths)
        for src in paths:
            row = summary.loc[src]
            assert row['mean_travel_time_hours'] == pytest.approx(row['median_travel_time_hours'])
            assert row['mean_travel_time_hours'] == pytest.approx(row['min_travel_time_hours'])
            assert row['mean_travel_time_hours'] == pytest.approx(row['max_travel_time_hours'])


# ---------------------------------------------------------------------------
# lagrangian_travel_time_exceedance
# ---------------------------------------------------------------------------

class TestLagrangianTravelTimeExceedance:
    def test_default_thresholds(self, steady_state):
        vol, q, paths = steady_state
        exc = lagrangian_travel_time_exceedance(vol, q, paths)
        assert set(exc.columns) == {6, 12, 24, 48, 72, 168}

    def test_custom_thresholds(self, steady_state):
        vol, q, paths = steady_state
        exc = lagrangian_travel_time_exceedance(vol, q, paths, thresholds_hours=[5, 10])
        assert set(exc.columns) == {5, 10}

    def test_exceedance_values_in_range(self, steady_state):
        vol, q, paths = steady_state
        exc = lagrangian_travel_time_exceedance(vol, q, paths, thresholds_hours=[1, 100])
        for val in exc.values.flatten():
            if not np.isnan(val):
                assert 0.0 <= val <= 1.0

    def test_index_name(self, steady_state):
        vol, q, paths = steady_state
        exc = lagrangian_travel_time_exceedance(vol, q, paths)
        assert exc.index.name == 'source_reach_id'


# ---------------------------------------------------------------------------
# compare_lagrangian_vs_dynamic
# ---------------------------------------------------------------------------

class TestCompareLagrangianVsDynamic:
    def test_columns(self, steady_state):
        vol, q, paths = steady_state
        result = compare_lagrangian_vs_dynamic(vol, q, paths)
        expected_cols = {
            'dynamic_mean_hours', 'lagrangian_mean_hours',
            'mean_difference_hours', 'mean_ratio',
        }
        assert set(result.columns) == expected_cols

    def test_steady_state_ratio_is_one(self, steady_state):
        vol, q, paths = steady_state
        result = compare_lagrangian_vs_dynamic(vol, q, paths)
        for src in paths:
            assert result.loc[src, 'mean_ratio'] == pytest.approx(1.0)
            assert result.loc[src, 'mean_difference_hours'] == pytest.approx(0.0)

    def test_varying_conditions_differ(self, varying_tau):
        vol, q, paths = varying_tau
        result = compare_lagrangian_vs_dynamic(vol, q, paths)
        # The storm causes the two approaches to diverge
        # (Lagrangian accounts for changed conditions at arrival time)
        assert result.loc['R1', 'mean_ratio'] != pytest.approx(1.0, abs=1e-6)

    def test_index_name(self, steady_state):
        vol, q, paths = steady_state
        result = compare_lagrangian_vs_dynamic(vol, q, paths)
        assert result.index.name == 'source_reach_id'
