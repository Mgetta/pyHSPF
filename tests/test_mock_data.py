# -*- coding: utf-8 -*-
"""
Unit tests exercising weighted-area, loading, and report calculations
using the mock schematic / HBN fixtures defined in conftest.py.

These tests are intentionally decoupled from UCI-file parsing so that
calculation logic can be validated independently.
"""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock

from tests.conftest import (
    PERLND_IDS,
    PERLND_NAMES,
    IMPLND_IDS,
    IMPLND_NAMES,
    REACH_IDS,
    _make_schematic_df,
    _build_all_hbn_frames,
    YEARLY_INDEX,
)


# ---------------------------------------------------------------------------
# Schematic / subwatersheds structural tests
# ---------------------------------------------------------------------------

class TestSchematicStructure:
    """Verify the mock schematic DataFrame has the expected shape."""

    def test_columns(self, schematic_df):
        reset = schematic_df.reset_index()
        for col in ("TVOLNO", "SVOL", "SVOLNO", "AFACTR", "MLNO", "LSID"):
            assert col in reset.columns

    def test_index_is_tvolno(self, schematic_df):
        assert schematic_df.index.name == "TVOLNO"

    def test_all_reaches_present(self, schematic_df):
        assert set(schematic_df.index.unique()) == set(REACH_IDS)

    def test_svol_values(self, schematic_df):
        assert set(schematic_df["SVOL"].unique()) == {"PERLND", "IMPLND"}

    def test_each_reach_has_implnd(self, schematic_df):
        for reach in REACH_IDS:
            reach_rows = schematic_df.loc[[reach]]
            assert "IMPLND" in reach_rows["SVOL"].values

    def test_afactr_positive(self, schematic_df):
        assert (schematic_df["AFACTR"] > 0).all()

    def test_lsid_matches_perlnd_names(self, schematic_df):
        perlnd_rows = schematic_df[schematic_df["SVOL"] == "PERLND"]
        assert set(perlnd_rows["LSID"].unique()).issubset(set(PERLND_NAMES))

    def test_implnd_lsid_is_urban(self, schematic_df):
        implnd_rows = schematic_df[schematic_df["SVOL"] == "IMPLND"]
        assert (implnd_rows["LSID"] == "Urban").all()


# ---------------------------------------------------------------------------
# HBN data-frame structural tests
# ---------------------------------------------------------------------------

class TestHbnStructure:
    """Verify the mock HBN dict has the expected keys and columns."""

    def test_perlnd_pwater_keys_exist(self, hbn_dataframes):
        for pid in PERLND_IDS:
            assert f"PERLND_PWATER_{pid:03d}_5" in hbn_dataframes

    def test_perlnd_sedmnt_keys_exist(self, hbn_dataframes):
        for pid in PERLND_IDS:
            assert f"PERLND_SEDMNT_{pid:03d}_5" in hbn_dataframes

    def test_perlnd_pqual_keys_exist(self, hbn_dataframes):
        for pid in PERLND_IDS:
            assert f"PERLND_PQUAL_{pid:03d}_5" in hbn_dataframes

    def test_implnd_keys_exist(self, hbn_dataframes):
        for iid in IMPLND_IDS:
            assert f"IMPLND_IWATER_{iid:03d}_5" in hbn_dataframes
            assert f"IMPLND_SOLIDS_{iid:03d}_5" in hbn_dataframes
            assert f"IMPLND_IQUAL_{iid:03d}_5" in hbn_dataframes

    def test_rchres_keys_exist(self, hbn_dataframes):
        for rid in REACH_IDS:
            assert f"RCHRES_HYDR_{rid:03d}_5" in hbn_dataframes
            assert f"RCHRES_RQUAL_{rid:03d}_5" in hbn_dataframes

    def test_perlnd_pwater_has_pero(self, hbn_dataframes):
        df = hbn_dataframes["PERLND_PWATER_001_5"]
        assert "PERO" in df.columns

    def test_implnd_iwater_has_suro(self, hbn_dataframes):
        df = hbn_dataframes["IMPLND_IWATER_001_5"]
        assert "SURO" in df.columns

    def test_rchres_hydr_has_rovol(self, hbn_dataframes):
        df = hbn_dataframes["RCHRES_HYDR_001_5"]
        assert "ROVOL" in df.columns

    def test_pqual_columns(self, hbn_dataframes):
        df = hbn_dataframes["PERLND_PQUAL_001_5"]
        for col in ("POQUALNH3+NH4", "POQUALNO3", "POQUALORTHO P", "POQUALBOD"):
            assert col in df.columns

    def test_iqual_columns(self, hbn_dataframes):
        df = hbn_dataframes["IMPLND_IQUAL_001_5"]
        for col in ("SOQUALNH3+NH4", "SOQUALNO3", "SOQUALORTHO P", "SOQUALBOD"):
            assert col in df.columns

    def test_rqual_columns(self, hbn_dataframes):
        df = hbn_dataframes["RCHRES_RQUAL_001_5"]
        for col in ("SSEDTOT", "TAMCONCDIS", "NO3CONCDIS", "PO4CONCDIS", "PTOTCONC"):
            assert col in df.columns

    def test_all_values_positive(self, hbn_dataframes):
        for key, df in hbn_dataframes.items():
            assert (df.values > 0).all(), f"Negative or zero value in {key}"

    def test_datetime_index(self, hbn_dataframes):
        for key, df in hbn_dataframes.items():
            assert isinstance(df.index, pd.DatetimeIndex), f"{key} index not DatetimeIndex"

    def test_total_frame_count(self, hbn_dataframes):
        expected = (
            len(PERLND_IDS) * 3      # PWATER + SEDMNT + PQUAL per PERLND
            + len(IMPLND_IDS) * 3     # IWATER + SOLIDS + IQUAL per IMPLND
            + len(REACH_IDS) * 2      # HYDR + RQUAL per RCHRES
        )
        assert len(hbn_dataframes) == expected


# ---------------------------------------------------------------------------
# Catchment-area / weighted-area calculations
# ---------------------------------------------------------------------------

class TestCatchmentAreas:
    """Test area computations derived from the mock schematic."""

    def test_catchment_area_per_reach(self, schematic_df):
        """Total area draining to each reach equals sum of AFACTR."""
        areas = schematic_df.reset_index().groupby("TVOLNO")["AFACTR"].sum()
        for reach in REACH_IDS:
            assert areas[reach] > 0

    def test_total_drainage_area(self, schematic_df):
        total = schematic_df["AFACTR"].sum()
        assert total > 0

    def test_landcover_area_by_reach(self, schematic_df):
        """Area per land cover per reach sums to total catchment area."""
        reset = schematic_df.reset_index()
        for reach in REACH_IDS:
            rdf = reset[reset["TVOLNO"] == reach]
            assert np.isclose(
                rdf["AFACTR"].sum(),
                rdf.groupby("LSID")["AFACTR"].sum().sum(),
            )

    def test_weighted_area_fraction(self, schematic_df):
        """Area fraction per land use within a reach sums to 1."""
        reset = schematic_df.reset_index()
        for reach in REACH_IDS:
            rdf = reset[reset["TVOLNO"] == reach]
            fractions = rdf["AFACTR"] / rdf["AFACTR"].sum()
            assert np.isclose(fractions.sum(), 1.0)


# ---------------------------------------------------------------------------
# Mock-UCI wiring tests
# ---------------------------------------------------------------------------

class TestMockUci:
    """Ensure the mock UCI fixture behaves like the real thing."""

    def test_subwatersheds_returns_df(self, mock_uci):
        df = mock_uci.network.subwatersheds()
        assert isinstance(df, pd.DataFrame)

    def test_get_opnids_returns_reaches(self, mock_uci):
        assert mock_uci.network.get_opnids() == REACH_IDS

    def test_drainage_area_positive(self, mock_uci):
        assert mock_uci.network.drainage_area() > 0

    def test_outlets(self, mock_uci):
        assert mock_uci.network.outlets() == [REACH_IDS[-1]]


# ---------------------------------------------------------------------------
# Mock-HBN wiring tests
# ---------------------------------------------------------------------------

class TestMockHbn:
    """Ensure the mock HBN fixture returns usable constituent data."""

    def test_get_perlnd_constituent_q(self, mock_hbn):
        df = mock_hbn.get_perlnd_constituent("Q")
        assert isinstance(df, pd.DataFrame)
        assert set(df.columns) == set(PERLND_IDS)

    def test_get_perlnd_constituent_tss(self, mock_hbn):
        df = mock_hbn.get_perlnd_constituent("TSS")
        assert not df.empty

    def test_get_implnd_constituent_q(self, mock_hbn):
        df = mock_hbn.get_implnd_constituent("Q")
        assert isinstance(df, pd.DataFrame)
        assert set(df.columns) == set(IMPLND_IDS)

    def test_get_implnd_constituent_tss(self, mock_hbn):
        df = mock_hbn.get_implnd_constituent("TSS")
        assert not df.empty

    def test_perlnd_values_positive(self, mock_hbn):
        df = mock_hbn.get_perlnd_constituent("Q")
        assert (df.values > 0).all()

    def test_implnd_values_positive(self, mock_hbn):
        df = mock_hbn.get_implnd_constituent("Q")
        assert (df.values > 0).all()


# ---------------------------------------------------------------------------
# Loading-rate calculation tests (using reports.loading helpers)
# ---------------------------------------------------------------------------

class TestLoadingCalculations:
    """Verify that loading calculations produce correct results when
    given mock data, independent of UCI / HBN file parsing."""

    def _build_constituent_loading_df(self, mock_hbn):
        """Mimic ``get_constituent_loading`` output for TSS."""
        perlnds = (
            mock_hbn.get_perlnd_constituent("TSS")
            .reset_index()
            .melt(id_vars=["index"], var_name="OPNID")
            .rename(columns={"index": "datetime"})
        )
        perlnds["OPERATION"] = "PERLND"

        implnds = (
            mock_hbn.get_implnd_constituent("TSS")
            .reset_index()
            .melt(id_vars=["index"], var_name="OPNID")
            .rename(columns={"index": "datetime"})
        )
        implnds["OPERATION"] = "IMPLND"

        return pd.concat([perlnds, implnds], ignore_index=True)

    def test_loading_df_shape(self, mock_hbn):
        df = self._build_constituent_loading_df(mock_hbn)
        assert "datetime" in df.columns
        assert "OPNID" in df.columns
        assert "value" in df.columns
        assert "OPERATION" in df.columns

    def test_loading_df_operations(self, mock_hbn):
        df = self._build_constituent_loading_df(mock_hbn)
        assert set(df["OPERATION"].unique()) == {"PERLND", "IMPLND"}

    def test_join_catchments(self, mock_uci, mock_hbn):
        """_join_catchments merges loading data with schematic and
        computes load = loading_rate × landcover_area."""
        from hspf.reports.loading import _join_catchments

        df = self._build_constituent_loading_df(mock_hbn)
        result = _join_catchments(df, mock_uci, "TSS")

        assert "load" in result.columns
        assert "loading_rate" in result.columns
        assert "landcover_area" in result.columns
        assert "catchment_area" in result.columns
        assert "landcover" in result.columns

        # Verify load = loading_rate * landcover_area
        for _, row in result.iterrows():
            assert np.isclose(row["load"], row["loading_rate"] * row["landcover_area"])

    def test_join_catchments_all_reaches_present(self, mock_uci, mock_hbn):
        from hspf.reports.loading import _join_catchments

        df = self._build_constituent_loading_df(mock_hbn)
        result = _join_catchments(df, mock_uci, "TSS")

        assert set(result["TVOLNO"].unique()) == set(REACH_IDS)

    def test_catchment_areas_function(self, mock_uci, schematic_df):
        """catchment_areas() returns correct per-reach totals."""
        from hspf.reports.loading import catchment_areas

        result = catchment_areas(mock_uci)
        expected = (
            schematic_df.reset_index()
            .groupby("TVOLNO")["AFACTR"]
            .sum()
            .reset_index()
            .rename(columns={"AFACTR": "catchment_area"})
        )

        pd.testing.assert_frame_equal(
            result.sort_values("TVOLNO").reset_index(drop=True),
            expected.sort_values("TVOLNO").reset_index(drop=True),
        )

    def test_filter_to_watershed(self, mock_uci, mock_hbn):
        """_filter_to_watershed filters and adds watershed_area column."""
        from hspf.reports.loading import _join_catchments, _filter_to_watershed

        df = self._build_constituent_loading_df(mock_hbn)
        joined = _join_catchments(df, mock_uci, "TSS")
        result = _filter_to_watershed(joined, mock_uci, reach_ids=REACH_IDS)

        assert "watershed_area" in result.columns
        assert (result["watershed_area"] > 0).all()

    def test_filter_to_watershed_custom_drainage_area(self, mock_uci, mock_hbn):
        from hspf.reports.loading import _join_catchments, _filter_to_watershed

        df = self._build_constituent_loading_df(mock_hbn)
        joined = _join_catchments(df, mock_uci, "TSS")
        result = _filter_to_watershed(
            joined, mock_uci, reach_ids=REACH_IDS, drainage_area=999.0
        )

        assert (result["watershed_area"] == 999.0).all()


# ---------------------------------------------------------------------------
# Weighted-area loading aggregation tests
# ---------------------------------------------------------------------------

class TestWeightedAreaAggregation:
    """Test that area-weighted aggregation produces consistent results."""

    def test_catchment_total_load_equals_sum_of_parts(self, mock_uci, mock_hbn, schematic_df):
        """Total load for a reach = Σ (loading_rate_i × area_i) for each
        PERLND/IMPLND contributing to that reach."""
        from hspf.reports.loading import _join_catchments

        # Build a simple loading df with a single time step
        perlnds = mock_hbn.get_perlnd_constituent("TSS").iloc[[0]]
        implnds = mock_hbn.get_implnd_constituent("TSS").iloc[[0]]

        pdf = perlnds.reset_index().melt(id_vars=["index"], var_name="OPNID").rename(columns={"index": "datetime"})
        pdf["OPERATION"] = "PERLND"
        idf = implnds.reset_index().melt(id_vars=["index"], var_name="OPNID").rename(columns={"index": "datetime"})
        idf["OPERATION"] = "IMPLND"
        loading_df = pd.concat([pdf, idf], ignore_index=True)

        joined = _join_catchments(loading_df, mock_uci, "TSS")

        # For each reach, check that total load = sum of individual loads
        for reach in REACH_IDS:
            reach_data = joined[joined["TVOLNO"] == reach]
            expected_total = (reach_data["loading_rate"] * reach_data["landcover_area"]).sum()
            actual_total = reach_data["load"].sum()
            assert np.isclose(actual_total, expected_total)

    def test_area_weighted_loading_rate(self, schematic_df):
        """Area-weighted average loading rate for a reach should be
        Σ(rate_i × area_i) / Σ(area_i)."""
        reset = schematic_df.reset_index()
        rng = np.random.RandomState(99)

        for reach in REACH_IDS:
            rdf = reset[reset["TVOLNO"] == reach].copy()
            rdf["rate"] = rng.uniform(0.1, 2.0, len(rdf))

            weighted_rate = (rdf["rate"] * rdf["AFACTR"]).sum() / rdf["AFACTR"].sum()
            total_load = (rdf["rate"] * rdf["AFACTR"]).sum()
            total_area = rdf["AFACTR"].sum()

            assert np.isclose(weighted_rate, total_load / total_area)


# ---------------------------------------------------------------------------
# Reproducibility tests
# ---------------------------------------------------------------------------

class TestReproducibility:
    """Confirm that fixtures are deterministic (seeded RNG)."""

    def test_schematic_is_deterministic(self):
        df1 = _make_schematic_df()
        df2 = _make_schematic_df()
        pd.testing.assert_frame_equal(df1, df2)

    def test_hbn_is_deterministic(self):
        f1 = _build_all_hbn_frames(YEARLY_INDEX)
        f2 = _build_all_hbn_frames(YEARLY_INDEX)
        for key in f1:
            pd.testing.assert_frame_equal(f1[key], f2[key])
