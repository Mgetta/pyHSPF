# -*- coding: utf-8 -*-
"""Unit tests for _apply_lag, lagged_contributions, and lagged_contribution_summary."""
import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from hspf.reports.residence import _apply_lag, lagged_contributions, lagged_contribution_summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_frames(n_times=10, dt_hours=1.0, sources=(1, 2)):
    """Return zero-filled contributions and travel_times DataFrames."""
    idx = pd.date_range('2020-01-01', periods=n_times, freq='h')
    contrib = pd.DataFrame(0.0, index=idx, columns=list(sources))
    tt = pd.DataFrame(0.0, index=idx, columns=list(sources))
    return contrib, tt


# ---------------------------------------------------------------------------
# Tests for _apply_lag
# ---------------------------------------------------------------------------

class TestApplyLag:
    """Unit tests for the private _apply_lag helper."""

    def test_zero_travel_time_stays_in_place(self):
        """Zero travel time → contribution stays at the emission timestep."""
        contrib, tt = _make_frames(n_times=5, sources=[1])
        contrib.iloc[2, 0] = 100.0
        tt.iloc[:, 0] = 0.0  # zero travel time for all timesteps

        result = _apply_lag(contrib, tt, dt_hours=1.0)

        assert result.iloc[2, 0] == pytest.approx(100.0)
        assert result.drop(index=result.index[2]).sum().sum() == pytest.approx(0.0)

    def test_whole_step_lag(self):
        """Lag of exactly N whole timesteps → contribution appears at t + N."""
        contrib, tt = _make_frames(n_times=10, sources=[1])
        contrib.iloc[0, 0] = 50.0
        tt.iloc[:, 0] = 3.0  # 3-hour travel time with 1-hour timestep → 3 steps

        result = _apply_lag(contrib, tt, dt_hours=1.0)

        # With zero fractional part, 100% goes to arr_lo = t + 3
        assert result.iloc[3, 0] == pytest.approx(50.0)
        assert result.iloc[:3, 0].sum() == pytest.approx(0.0)
        assert result.iloc[4:, 0].sum() == pytest.approx(0.0)

    def test_fractional_lag_splits_contribution(self):
        """Fractional lag → split between floor and ceil bins."""
        contrib, tt = _make_frames(n_times=10, sources=[1])
        contrib.iloc[0, 0] = 100.0
        tt.iloc[:, 0] = 1.7  # lag_steps = 1.7 → 30% at t+1, 70% at t+2

        result = _apply_lag(contrib, tt, dt_hours=1.0)

        assert result.iloc[1, 0] == pytest.approx(30.0, rel=1e-6)
        assert result.iloc[2, 0] == pytest.approx(70.0, rel=1e-6)

    def test_lag_beyond_end_dropped(self):
        """Contribution whose arrival falls beyond the timeseries end is dropped."""
        contrib, tt = _make_frames(n_times=5, sources=[1])
        contrib.iloc[4, 0] = 100.0  # last timestep
        tt.iloc[:, 0] = 2.0          # would arrive at t=6, beyond n=5

        result = _apply_lag(contrib, tt, dt_hours=1.0)

        assert result.sum().sum() == pytest.approx(0.0)

    def test_partial_beyond_end(self):
        """Floor bin within range but ceil bin beyond end → only floor bin filled."""
        contrib, tt = _make_frames(n_times=5, sources=[1])
        contrib.iloc[3, 0] = 100.0   # emission at t=3
        tt.iloc[:, 0] = 1.5          # arr_lo=4 (in range), arr_hi=5 (out of range)

        result = _apply_lag(contrib, tt, dt_hours=1.0)

        assert result.iloc[4, 0] == pytest.approx(50.0)
        assert result.iloc[:4, 0].sum() == pytest.approx(0.0)

    def test_nan_travel_time_skipped(self):
        """NaN travel time → that timestep's contribution is skipped."""
        contrib, tt = _make_frames(n_times=5, sources=[1])
        contrib.iloc[1, 0] = 100.0
        tt.iloc[1, 0] = np.nan

        result = _apply_lag(contrib, tt, dt_hours=1.0)

        assert result.sum().sum() == pytest.approx(0.0)

    def test_negative_travel_time_skipped(self):
        """Negative travel time → skipped."""
        contrib, tt = _make_frames(n_times=5, sources=[1])
        contrib.iloc[1, 0] = 100.0
        tt.iloc[1, 0] = -1.0

        result = _apply_lag(contrib, tt, dt_hours=1.0)

        assert result.sum().sum() == pytest.approx(0.0)

    def test_zero_contribution_skipped(self):
        """Zero contribution → nothing added to output."""
        contrib, tt = _make_frames(n_times=5, sources=[1])
        contrib.iloc[1, 0] = 0.0
        tt.iloc[:, 0] = 1.0

        result = _apply_lag(contrib, tt, dt_hours=1.0)

        assert result.sum().sum() == pytest.approx(0.0)

    def test_negative_contribution_skipped(self):
        """Negative contribution → skipped."""
        contrib, tt = _make_frames(n_times=5, sources=[1])
        contrib.iloc[1, 0] = -10.0
        tt.iloc[:, 0] = 1.0

        result = _apply_lag(contrib, tt, dt_hours=1.0)

        assert result.sum().sum() == pytest.approx(0.0)

    def test_nan_contribution_skipped(self):
        """NaN contribution → skipped."""
        contrib, tt = _make_frames(n_times=5, sources=[1])
        contrib.iloc[1, 0] = np.nan
        tt.iloc[:, 0] = 1.0

        result = _apply_lag(contrib, tt, dt_hours=1.0)

        assert result.sum().sum() == pytest.approx(0.0)

    def test_output_shape_matches_input(self):
        """Output shape, index, and columns match the input DataFrames."""
        contrib, tt = _make_frames(n_times=8, sources=[10, 20, 30])
        contrib.iloc[2, 0] = 5.0
        tt.iloc[:, :] = 2.0

        result = _apply_lag(contrib, tt, dt_hours=1.0)

        assert result.shape == contrib.shape
        assert list(result.index) == list(contrib.index)
        assert list(result.columns) == list(contrib.columns)

    def test_multiple_sources_independent(self):
        """Each source's lag is applied independently."""
        contrib, tt = _make_frames(n_times=10, sources=[1, 2])
        contrib.iloc[0, 0] = 100.0  # source 1, emission at t=0
        contrib.iloc[0, 1] = 200.0  # source 2, emission at t=0
        tt.iloc[:, 0] = 1.0         # source 1 lag = 1 step
        tt.iloc[:, 1] = 3.0         # source 2 lag = 3 steps

        result = _apply_lag(contrib, tt, dt_hours=1.0)

        assert result.iloc[1, 0] == pytest.approx(100.0)  # source 1 at t=1
        assert result.iloc[3, 1] == pytest.approx(200.0)  # source 2 at t=3

    def test_conservation_within_range(self):
        """Total arriving mass equals total emitted mass when all arrivals fit."""
        contrib, tt = _make_frames(n_times=20, sources=[1, 2])
        rng = np.random.default_rng(42)
        contrib.iloc[:, 0] = rng.uniform(0, 10, 20)
        contrib.iloc[:, 1] = rng.uniform(0, 10, 20)
        tt.iloc[:, 0] = 1.0   # 1-step lag — all arrivals fit in n=20 except last
        tt.iloc[:, 1] = 2.0

        result = _apply_lag(contrib, tt, dt_hours=1.0)

        # All emissions except the last lag-steps' worth should be conserved
        # source 1: emissions at t=0..18 all arrive within t=1..19
        assert result.iloc[:, 0].sum() == pytest.approx(
            contrib.iloc[:19, 0].sum(), rel=1e-6
        )
        # source 2: emissions at t=0..17 all arrive within t=2..19
        assert result.iloc[:, 1].sum() == pytest.approx(
            contrib.iloc[:18, 1].sum(), rel=1e-6
        )


# ---------------------------------------------------------------------------
# Helpers to build mock uci/hbn objects
# ---------------------------------------------------------------------------

def _build_mock_uci_hbn(n_times=10, dt='h', sources=(1, 2, 3), target=10):
    """Build minimal mock uci and hbn objects for testing public functions."""
    idx = pd.date_range('2020-01-01', periods=n_times, freq=dt)
    all_ids = list(sources) + [target]

    # Build mock uci with network
    uci = MagicMock()
    uci.network.paths.return_value = {s: [s, target] for s in sources}
    uci.network.upstream.return_value = []

    # Build mock hbn
    hbn = MagicMock()

    def _ts(operation, t_code, var, opnids=None):
        ids = opnids if opnids is not None else all_ids
        return pd.DataFrame(
            np.ones((n_times, len(ids))) * 100.0,
            index=idx, columns=ids,
        )

    hbn.get_multiple_timeseries.side_effect = _ts

    return uci, hbn


# ---------------------------------------------------------------------------
# Tests for lagged_contributions
# ---------------------------------------------------------------------------

class TestLaggedContributions:
    """Integration-level tests for lagged_contributions public function."""

    def _make_contributions_and_tt(self, n_times, n_sources, lag_value):
        """Return simple contributions and travel_times DataFrames."""
        sources = list(range(n_sources))
        idx = pd.date_range('2020-01-01', periods=n_times, freq='h')
        contrib = pd.DataFrame(
            np.ones((n_times, n_sources)),
            index=idx, columns=sources,
        )
        tt = pd.DataFrame(
            np.full((n_times, n_sources), lag_value),
            index=idx, columns=sources,
        )
        return contrib, tt

    def test_source_filtering_returns_only_requested_columns(self):
        """When source_reach_ids is provided, only those columns appear."""
        with patch('hspf.reports.residence.dynamic_travel_times') as mock_tt, \
             patch('hspf.reports.contributions.channel_fate') as mock_fate, \
             patch('hspf.reports.contributions.local_loading') as mock_ll, \
             patch('hspf.reports.contributions._compute_path_fate_factors') as mock_pff, \
             patch('hspf.reports.contributions._compute_contributions') as mock_cc:

            n_times, sources, target = 10, [1, 2, 3], 10
            idx = pd.date_range('2020-01-01', periods=n_times, freq='h')
            dummy_df = pd.DataFrame(
                np.ones((n_times, len(sources))), index=idx, columns=sources
            )
            mock_tt.return_value = dummy_df.copy()
            mock_cc.return_value = dummy_df.copy()
            mock_fate.return_value = dummy_df.copy()
            mock_pff.return_value = dummy_df.copy()
            mock_ll.return_value = dummy_df.copy()

            uci = MagicMock()
            uci.network.paths.return_value = {s: [s, target] for s in sources}
            uci.network.upstream.return_value = []
            hbn = MagicMock()

            result = lagged_contributions(
                uci, hbn, target_reach_id=target,
                source_reach_ids=[1, 3],
            )

        assert list(result.columns) == [1, 3]

    def test_invalid_source_reach_id_raises(self):
        """A source_reach_id not in the paths raises ValueError."""
        with patch('hspf.reports.residence.dynamic_travel_times') as mock_tt, \
             patch('hspf.reports.contributions.channel_fate'), \
             patch('hspf.reports.contributions.local_loading'), \
             patch('hspf.reports.contributions._compute_path_fate_factors'), \
             patch('hspf.reports.contributions._compute_contributions') as mock_cc:

            n_times, sources, target = 5, [1, 2], 10
            idx = pd.date_range('2020-01-01', periods=n_times, freq='h')
            dummy_df = pd.DataFrame(
                np.ones((n_times, len(sources))), index=idx, columns=sources
            )
            mock_tt.return_value = dummy_df.copy()
            mock_cc.return_value = dummy_df.copy()

            uci = MagicMock()
            uci.network.paths.return_value = {s: [s, target] for s in sources}
            uci.network.upstream.return_value = []
            hbn = MagicMock()

            with pytest.raises(ValueError, match="source_reach_ids not found"):
                lagged_contributions(
                    uci, hbn, target_reach_id=target,
                    source_reach_ids=[99],
                )

    def test_time_window_slicing(self):
        """start/end slicing returns only the requested window."""
        with patch('hspf.reports.residence.dynamic_travel_times') as mock_tt, \
             patch('hspf.reports.contributions.channel_fate'), \
             patch('hspf.reports.contributions.local_loading'), \
             patch('hspf.reports.contributions._compute_path_fate_factors'), \
             patch('hspf.reports.contributions._compute_contributions') as mock_cc:

            n_times, sources, target = 10, [1], 10
            idx = pd.date_range('2020-01-01', periods=n_times, freq='h')
            dummy_df = pd.DataFrame(
                np.ones((n_times, len(sources))), index=idx, columns=sources
            )
            mock_tt.return_value = dummy_df.copy()
            mock_cc.return_value = dummy_df.copy()

            uci = MagicMock()
            uci.network.paths.return_value = {s: [s, target] for s in sources}
            uci.network.upstream.return_value = []
            hbn = MagicMock()

            result = lagged_contributions(
                uci, hbn, target_reach_id=target,
                start='2020-01-01 03:00',
                end='2020-01-01 06:00',
            )

        assert result.index[0] >= pd.Timestamp('2020-01-01 03:00')
        assert result.index[-1] <= pd.Timestamp('2020-01-01 06:00')

    def test_pre_window_emission_arrives_in_window(self):
        """Contributions emitted before window start but arriving within are captured."""
        n_times, sources, target = 10, [1], 10
        idx = pd.date_range('2020-01-01', periods=n_times, freq='h')

        # Contributions: only at t=0 (before the window start of t=3)
        contrib = pd.DataFrame(0.0, index=idx, columns=sources)
        contrib.iloc[0, 0] = 100.0

        # Travel time: 3 hours → emission at t=0 arrives at t=3
        tt = pd.DataFrame(3.0, index=idx, columns=sources)

        with patch('hspf.reports.residence.dynamic_travel_times',
                   return_value=tt), \
             patch('hspf.reports.contributions.channel_fate'), \
             patch('hspf.reports.contributions.local_loading'), \
             patch('hspf.reports.contributions._compute_path_fate_factors'), \
             patch('hspf.reports.contributions._compute_contributions',
                   return_value=contrib):

            uci = MagicMock()
            uci.network.paths.return_value = {s: [s, target] for s in sources}
            uci.network.upstream.return_value = []
            hbn = MagicMock()

            result = lagged_contributions(
                uci, hbn, target_reach_id=target,
                start='2020-01-01 03:00',
            )

        # t=3 is in the window and should have the full contribution
        assert result.loc['2020-01-01 03:00', 1] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Tests for lagged_contribution_summary
# ---------------------------------------------------------------------------

class TestLaggedContributionSummary:
    """Tests for lagged_contribution_summary."""

    def _patch_lagged(self, lagged_df):
        """Context manager that patches lagged_contributions with a fixed DataFrame."""
        return patch(
            'hspf.reports.residence.lagged_contributions',
            return_value=lagged_df,
        )

    def test_summary_columns(self):
        """Summary DataFrame has the expected columns."""
        idx = pd.date_range('2020-01-01', periods=5, freq='h')
        lagged_df = pd.DataFrame(
            {'src1': [10.0, 20.0, 5.0, 0.0, 15.0],
             'src2': [5.0, 10.0, 2.0, 0.0, 8.0]},
            index=idx,
        )

        with self._patch_lagged(lagged_df):
            result = lagged_contribution_summary(
                MagicMock(), MagicMock(), target_reach_id=99
            )

        assert set(result.columns) == {
            'mean_lagged_contribution',
            'total_lagged_contribution',
            'pct_of_total',
        }

    def test_pct_of_total_sums_to_100(self):
        """pct_of_total sums to 100 (or 0 if all contributions are zero)."""
        idx = pd.date_range('2020-01-01', periods=4, freq='h')
        lagged_df = pd.DataFrame(
            {'a': [1.0, 2.0, 3.0, 4.0],
             'b': [4.0, 3.0, 2.0, 1.0],
             'c': [0.5, 0.5, 0.5, 0.5]},
            index=idx,
        )

        with self._patch_lagged(lagged_df):
            result = lagged_contribution_summary(
                MagicMock(), MagicMock(), target_reach_id=99
            )

        assert result['pct_of_total'].sum() == pytest.approx(100.0)

    def test_summary_index_name(self):
        """Summary DataFrame index is named 'source_reach_id'."""
        idx = pd.date_range('2020-01-01', periods=3, freq='h')
        lagged_df = pd.DataFrame({'x': [1.0, 2.0, 3.0]}, index=idx)

        with self._patch_lagged(lagged_df):
            result = lagged_contribution_summary(
                MagicMock(), MagicMock(), target_reach_id=1
            )

        assert result.index.name == 'source_reach_id'

    def test_total_lagged_contribution_matches_sum(self):
        """total_lagged_contribution equals column sum of lagged DataFrame."""
        idx = pd.date_range('2020-01-01', periods=4, freq='h')
        lagged_df = pd.DataFrame(
            {10: [1.0, 2.0, 3.0, 4.0], 20: [5.0, 6.0, 7.0, 8.0]},
            index=idx,
        )

        with self._patch_lagged(lagged_df):
            result = lagged_contribution_summary(
                MagicMock(), MagicMock(), target_reach_id=99
            )

        assert result.loc[10, 'total_lagged_contribution'] == pytest.approx(10.0)
        assert result.loc[20, 'total_lagged_contribution'] == pytest.approx(26.0)

    def test_all_zero_contributions_pct_is_zero(self):
        """When all contributions are zero, pct_of_total should be 0."""
        idx = pd.date_range('2020-01-01', periods=3, freq='h')
        lagged_df = pd.DataFrame({'a': [0.0, 0.0, 0.0]}, index=idx)

        with self._patch_lagged(lagged_df):
            result = lagged_contribution_summary(
                MagicMock(), MagicMock(), target_reach_id=1
            )

        assert result['pct_of_total'].sum() == pytest.approx(0.0)
