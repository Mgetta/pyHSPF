# -*- coding: utf-8 -*-
"""
Shared pytest fixtures providing mock SCHEMATIC and HBN data.

Scenario
--------
* 7 PERLNDs:  1-Forest, 2-Agriculture, 3-Grassland, 4-Wetland,
              5-Barren, 6-Feedlot, 7-Urban
* 1 IMPLND:   1-Urban
* 7 RCHRESs:  1-7

Each reach drains an arbitrary number of acres from a subset of the
PERLNDs and the single IMPLND.  The data is intentionally simple so
that expected results can be computed by hand.
"""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock


# ── land-use definitions ────────────────────────────────────────────────────

PERLND_IDS = [1, 2, 3, 4, 5, 6, 7]
PERLND_NAMES = [
    "Forest", "Agriculture", "Grassland", "Wetland",
    "Barren", "Feedlot", "Urban",
]
IMPLND_IDS = [1]
IMPLND_NAMES = ["Urban"]
REACH_IDS = [1, 2, 3, 4, 5, 6, 7]

# ── time axis shared by every mock HBN frame ────────────────────────────────

YEARLY_INDEX = pd.date_range("2000-01-01", periods=5, freq="YS")  # 2000-2004


# ── helpers ─────────────────────────────────────────────────────────────────

def _make_schematic_df():
    """Build a subwatersheds-style DataFrame.

    Columns (after reset_index): TVOLNO, SVOL, SVOLNO, AFACTR, MLNO, LSID
    The index of the returned frame is TVOLNO (matching the real
    ``subwatersheds()`` output).
    """
    rng = np.random.RandomState(42)
    rows = []
    for reach in REACH_IDS:
        # Each reach gets a random subset of 3-7 PERLNDs
        n_perl = rng.randint(3, 8)
        chosen = rng.choice(PERLND_IDS, size=n_perl, replace=False)
        for pid in sorted(chosen):
            area = round(rng.uniform(5.0, 50.0), 1)
            rows.append({
                "TVOLNO": reach,
                "SVOL": "PERLND",
                "SVOLNO": pid,
                "AFACTR": area,
                "MLNO": 1,
                "LSID": PERLND_NAMES[pid - 1],
            })
        # Every reach also drains the single IMPLND
        impl_area = round(rng.uniform(2.0, 15.0), 1)
        rows.append({
            "TVOLNO": reach,
            "SVOL": "IMPLND",
            "SVOLNO": 1,
            "AFACTR": impl_area,
            "MLNO": 1,
            "LSID": "Urban",
        })

    df = pd.DataFrame(rows)
    df = df.set_index("TVOLNO")
    return df


def _make_perlnd_hbn(perlnd_id, index):
    """Return dict of DataFrames for one PERLND at all activities."""
    rng = np.random.RandomState(perlnd_id)
    n = len(index)

    frames = {}
    # PWATER
    frames[f"PERLND_PWATER_{perlnd_id:03d}_5"] = pd.DataFrame(
        {"PERO": rng.uniform(0.5, 5.0, n)}, index=index,
    )
    # SEDMNT
    frames[f"PERLND_SEDMNT_{perlnd_id:03d}_5"] = pd.DataFrame(
        {"SOSED": rng.uniform(0.01, 2.0, n)}, index=index,
    )
    # PQUAL
    frames[f"PERLND_PQUAL_{perlnd_id:03d}_5"] = pd.DataFrame({
        "POQUALNH3+NH4":  rng.uniform(0.01, 0.5, n),
        "POQUALNO3":      rng.uniform(0.01, 0.3, n),
        "POQUALORTHO P":  rng.uniform(0.001, 0.1, n),
        "POQUALBOD":      rng.uniform(0.1, 2.0, n),
    }, index=index)
    return frames


def _make_implnd_hbn(implnd_id, index):
    """Return dict of DataFrames for one IMPLND at all activities."""
    rng = np.random.RandomState(100 + implnd_id)
    n = len(index)

    frames = {}
    # IWATER
    frames[f"IMPLND_IWATER_{implnd_id:03d}_5"] = pd.DataFrame(
        {"SURO": rng.uniform(1.0, 8.0, n)}, index=index,
    )
    # SOLIDS
    frames[f"IMPLND_SOLIDS_{implnd_id:03d}_5"] = pd.DataFrame(
        {"SLDS": rng.uniform(0.05, 3.0, n)}, index=index,
    )
    # IQUAL
    frames[f"IMPLND_IQUAL_{implnd_id:03d}_5"] = pd.DataFrame({
        "SOQUALNH3+NH4":  rng.uniform(0.02, 0.6, n),
        "SOQUALNO3":      rng.uniform(0.02, 0.4, n),
        "SOQUALORTHO P":  rng.uniform(0.002, 0.15, n),
        "SOQUALBOD":      rng.uniform(0.2, 3.0, n),
    }, index=index)
    return frames


def _make_rchres_hbn(reach_id, index):
    """Return dict of DataFrames for one RCHRES at key activities."""
    rng = np.random.RandomState(200 + reach_id)
    n = len(index)

    frames = {}
    # HYDR
    frames[f"RCHRES_HYDR_{reach_id:03d}_5"] = pd.DataFrame(
        {"ROVOL": rng.uniform(10.0, 500.0, n)}, index=index,
    )
    # RQUAL – concentrations
    frames[f"RCHRES_RQUAL_{reach_id:03d}_5"] = pd.DataFrame({
        "SSEDTOT":     rng.uniform(1.0, 50.0, n),
        "TAMCONCDIS":  rng.uniform(0.01, 0.5, n),
        "NTOTORGCONC": rng.uniform(0.01, 0.3, n),
        "NO2CONCDIS":  rng.uniform(0.001, 0.05, n),
        "NO3CONCDIS":  rng.uniform(0.1, 2.0, n),
        "PO4CONCDIS":  rng.uniform(0.005, 0.2, n),
        "PTOTCONC":    rng.uniform(0.01, 0.5, n),
    }, index=index)
    return frames


def _build_all_hbn_frames(index):
    """Combine every operation's HBN frames into one flat dict."""
    all_frames = {}
    for pid in PERLND_IDS:
        all_frames.update(_make_perlnd_hbn(pid, index))
    for iid in IMPLND_IDS:
        all_frames.update(_make_implnd_hbn(iid, index))
    for rid in REACH_IDS:
        all_frames.update(_make_rchres_hbn(rid, index))
    return all_frames


# ── pytest fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def schematic_df():
    """Subwatersheds-style DataFrame indexed by TVOLNO."""
    return _make_schematic_df()


@pytest.fixture
def hbn_dataframes():
    """Dict of HBN DataFrames keyed as ``{OPN}_{ACTIVITY}_{ID:03d}_{TCODE}``."""
    return _build_all_hbn_frames(YEARLY_INDEX)


@pytest.fixture
def mock_uci(schematic_df):
    """MagicMock UCI wired so ``uci.network.subwatersheds()`` returns *schematic_df*."""
    uci = MagicMock()

    uci.network.subwatersheds.return_value = schematic_df

    # get_opnids returns all reach IDs by default
    uci.network.get_opnids.return_value = REACH_IDS

    # drainage_area returns the total AFACTR from the schematic
    total = schematic_df.reset_index()["AFACTR"].sum()
    uci.network.drainage_area.return_value = total

    # outlets returns the last reach
    uci.network.outlets.return_value = [REACH_IDS[-1]]

    return uci


@pytest.fixture
def mock_hbn(hbn_dataframes):
    """MagicMock HBN interface whose ``get_perlnd_constituent`` /
    ``get_implnd_constituent`` methods return deterministic DataFrames
    built from *hbn_dataframes*.
    """
    hbn = MagicMock()
    hbn.data_frames = hbn_dataframes

    # Pre-index frames by (operation, opnid) for O(1) lookup
    _index = {}
    for key, df in hbn_dataframes.items():
        parts = key.split("_", 2)  # e.g. ['PERLND', 'PWATER', '001_5']
        opn = parts[0]
        opnid = int(parts[2].split("_")[0])
        _index.setdefault((opn, opnid), []).append(df)

    def _get_perlnd_constituent(constituent, time_step=5):
        from hspf.helpers import get_tcons
        t_cons = get_tcons(constituent, "PERLND")
        frames = []
        for pid in PERLND_IDS:
            for df in _index.get(("PERLND", pid), []):
                for t_con in t_cons:
                    if t_con in df.columns:
                        series = df[t_con].copy()
                        series.name = pid
                        frames.append(series)
        if not frames:
            return pd.DataFrame()
        result = pd.concat(frames, axis=1)
        if len(t_cons) > 1:
            result = result.T.groupby(level=0).sum().T
        return result

    def _get_implnd_constituent(constituent, time_step=5):
        from hspf.helpers import get_tcons
        t_cons = get_tcons(constituent, "IMPLND")
        frames = []
        for iid in IMPLND_IDS:
            for df in _index.get(("IMPLND", iid), []):
                for t_con in t_cons:
                    if t_con in df.columns:
                        series = df[t_con].copy()
                        series.name = iid
                        frames.append(series)
        if not frames:
            return pd.DataFrame()
        result = pd.concat(frames, axis=1)
        if len(t_cons) > 1:
            result = result.T.groupby(level=0).sum().T
        return result

    hbn.get_perlnd_constituent = _get_perlnd_constituent
    hbn.get_implnd_constituent = _get_implnd_constituent
    return hbn
