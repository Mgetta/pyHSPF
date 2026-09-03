"""One explicit function per golden output.

Each ``generate_*`` function runs one pyHSPF function against a loaded
``hspfModel`` object and saves the result under the model's ``goldens/`` folder.
Rerun a function whenever the fixture model changes and you want to accept the
new output as the expected result.

Example::

    from hspf.hspfModel import hspfModel
    from tests.helpers import generate_goldens as gg

    model_dir = r"tests\\data\\models\\simple_monthly"
    model = hspfModel(model_dir + r"\\simple_monthly.uci")

    gg.generate_catchment_loading(model, model_dir, "TP")
    gg.generate_subwatersheds(model, model_dir)
    gg.generate_get_opnids(model, model_dir, "PERLND", reach_ids=[10])
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Optional, Sequence


from pathlib import Path
import pandas as pd



DEFAULT_FLOAT_FORMAT = "%.10g"


def slugify(value: object) -> str:
    """Make a value safe for use in a golden filename."""
    if isinstance(value, (list, tuple, set)):
        value = "-".join(str(item) for item in value)
    text = str(value).strip().replace(" ", "-")
    text = re.sub(r"[^A-Za-z0-9_.=-]+", "-", text)
    return text.strip("-").lower() or "na"


def golden_filename(function_name: str, extension: str, **context: object) -> str:
    """Name a golden by source function and the arguments that define it."""
    stem = slugify(function_name)
    for key, value in context.items():
        stem += f"__{slugify(key)}={slugify(value)}"
    extension = extension if extension.startswith(".") else f".{extension}"
    return f"{stem}{extension}"


def normalize_frame(
    df: pd.DataFrame,
    sort_by: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Make a DataFrame stable enough to save as a golden file."""
    result = df.copy()

    if not isinstance(result.index, pd.RangeIndex) or result.index.name is not None:
        result = result.reset_index(drop=False)
        if "index" in result.columns and "datetime" not in result.columns:
            result = result.rename(columns={"index": "datetime"})
    else:
        result = result.reset_index(drop=True)

    if sort_by is not None:
        sort_columns = [column for column in sort_by if column in result.columns]
        if sort_columns:
            result = result.sort_values(sort_columns, kind="mergesort")

    return result.reset_index(drop=True)


def write_golden(
    df: pd.DataFrame,
    path: Path,
    *,
    sort_by: Optional[Sequence[str]] = None,
    float_format: str = DEFAULT_FLOAT_FORMAT,
) -> Path:
    """Write a golden DataFrame as CSV or Parquet."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_frame(df, sort_by=sort_by)

    if path.suffix.lower() == ".csv":
        normalized.to_csv(
            path,
            index=False,
            float_format=float_format,
            date_format="%Y-%m-%dT%H:%M:%S",
        )
    elif path.suffix.lower() == ".parquet":
        normalized.to_parquet(path, index=False)
    else:
        raise ValueError(f"Unsupported golden format: {path.suffix}")

    return path

GOLDEN_GROUPS = ("raw", "recipes", "reports", "network")


def create_golden_folders(model_dir: Path) -> Path:
    """Create the goldens subfolders for one model."""
    goldens_dir = Path(model_dir) / "goldens"
    for name in GOLDEN_GROUPS:
        (goldens_dir / name).mkdir(parents=True, exist_ok=True)
    return goldens_dir


def _save(df: pd.DataFrame, model_dir: Path, group: str, name: str, **context) -> Path:
    """Write one golden DataFrame and return its path."""
    create_golden_folders(model_dir)
    path = Path(model_dir) / "goldens" / group / golden_filename(name, "parquet", **context)
    return write_golden(df, path)


def load_golden(model_dir: Path, group: str, name: str, **context) -> pd.DataFrame:
    """Load one golden DataFrame."""
    path = Path(model_dir) / "goldens" / group / golden_filename(name, "parquet", **context)
    if not path.exists():
        raise FileNotFoundError(f"Golden file not found: {path}")
    return pd.read_parquet(path)

# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def generate_catchment_loading(model, model_dir, constituent, simulation_period='yearly'):
    """Golden for reports.get_catchment_loading via model.reports."""
    df = model.reports.catchment_loading(constituent, simulation_period=simulation_period)
    return _save(df, model_dir, "reports", "reports.catchment_loading",
                 constituent=constituent, simulation_period=simulation_period)


def generate_watershed_loading(model, model_dir, constituent, reach_ids,
                               upstream_reach_ids=None, by_landcover=False,
                               simulation_period='yearly'):
    """Golden for reports.get_watershed_loading via model.reports."""
    df = model.reports.watershed_loading(
        constituent=constituent, 
        reach_ids=reach_ids, 
        upstream_reach_ids=
        upstream_reach_ids, 
        by_landcover=by_landcover, 
        simulation_period=simulation_period,
    )
    return _save(df, model_dir, "reports", "reports.watershed_loading",
                 constituent=constituent, reach_ids=reach_ids,
                 upstream_reach_ids=upstream_reach_ids,
                 by_landcover=by_landcover, simulation_period=simulation_period)


def generate_total_contributions(model, model_dir, constituent, target_reach_id):
    """Golden for contributions.total_contributions via model.reports."""
    df = model.reports.total_contributions(constituent, target_reach_id)
    return _save(df, model_dir, "reports", "reports.total_contributions",
                 constituent=constituent, target_reach_id=target_reach_id)


def generate_catchment_contributions(model, model_dir, constituent, target_reach_id):
    """Golden for contributions.catchment_contributions via model.reports."""
    df = model.reports.catchment_contributions(constituent, target_reach_id)
    return _save(df, model_dir, "reports", "reports.catchment_contributions",
                 constituent=constituent, target_reach_id=target_reach_id)


# ---------------------------------------------------------------------------
# Recipes (MASS-LINK derived nutrients)
# ---------------------------------------------------------------------------

def generate_total_phosphorus(model, model_dir, operation="PERLND", t_code=4):
    """Golden for nutrients.total_phosphorus."""
    from hspf.reports.nutrients import total_phosphorus

    df = total_phosphorus(model.uci, model.hbns, t_code=t_code, operation=operation)
    return _save(df, model_dir, "recipes", "nutrients.total_phosphorus",
                 operation=operation, t_code=t_code)


def generate_total_nitrogen(model, model_dir, operation="PERLND", t_code=4):
    """Golden for nutrients.total_nitrogen."""
    from hspf.reports.nutrients import total_nitrogen

    df = total_nitrogen(model.uci, model.hbns, t_code=t_code, operation=operation)
    return _save(df, model_dir, "recipes", "nutrients.total_nitrogen",
                 operation=operation, t_code=t_code)


# ---------------------------------------------------------------------------
# Network (catchment/watershed grouping and traversal)
# ---------------------------------------------------------------------------

def generate_subwatersheds(model, model_dir):
    """Golden for uci.network.subwatersheds(): the reach <-> catchment table."""
    df = model.uci.network.subwatersheds().reset_index()
    return _save(df, model_dir, "network", "network.subwatersheds")


def generate_get_opnids(model, model_dir, operation, reach_ids,
                        upstream_reach_ids=None):
    """Golden for uci.network.get_opnids(): watershed membership."""
    opnids = model.uci.network.get_opnids(operation, reach_ids, upstream_reach_ids)
    df = pd.DataFrame({"OPNID": sorted(opnids)})
    return _save(df, model_dir, "network", "network.get_opnids",
                 operation=operation, reach_ids=reach_ids,
                 upstream_reach_ids=upstream_reach_ids)


def generate_upstream_network(model, model_dir, reach_id):
    """Golden for uci.network._upstream(): all upstream reaches, inclusive."""
    reaches = model.uci.network._upstream(reach_id)
    df = pd.DataFrame({"reach_id": sorted(reaches)})
    return _save(df, model_dir, "network", "network.upstream_network",
                 reach_id=reach_id)


def generate_watershed_area(model, model_dir, reach_ids, upstream_reach_ids=None):
    """Golden for uci.network.drainage_area(): total watershed area."""
    area = model.uci.network.drainage_area(reach_ids, upstream_reach_ids)
    df = pd.DataFrame({"drainage_area": [area]})
    return _save(df, model_dir, "network", "network.drainage_area",
                 reach_ids=reach_ids, upstream_reach_ids=upstream_reach_ids)


def generate_drainage_area_landcover(model, model_dir, reach_ids,
                                     upstream_reach_ids=None):
    """Golden for uci.network.drainage_area_landcover(): area grouped by landcover."""
    areas = model.uci.network.drainage_area_landcover(reach_ids, upstream_reach_ids)
    df = areas.reset_index()
    return _save(df, model_dir, "network", "network.drainage_area_landcover",
                 reach_ids=reach_ids, upstream_reach_ids=upstream_reach_ids)


def generate_calibration_order(model, model_dir, reach_ids):
    """Golden for uci.network.calibration_order(): parallel calibration groups."""
    order = model.uci.network.calibration_order(reach_ids)
    rows = [
        {"order": position, "reach_id": reach_id}
        for position, group in enumerate(order)
        for reach_id in sorted(group)
    ]
    df = pd.DataFrame(rows)
    return _save(df, model_dir, "network", "network.calibration_order",
                 reach_ids=reach_ids)


def generate_outlets(model, model_dir):
    """Golden for uci.network.outlets(): reaches with no downstream connection."""
    df = pd.DataFrame({"reach_id": sorted(model.uci.network.outlets())})
    return _save(df, model_dir, "network", "network.outlets")


# ---------------------------------------------------------------------------
# Raw HBN output
# ---------------------------------------------------------------------------

def generate_raw_timeseries(model, model_dir, operation, t_code, variable,
                            activity=None):
    """Golden for hbnInterface.get_multiple_timeseries in long format."""
    df = model.hbns.get_multiple_timeseries(
        operation, t_code, variable, activity=activity, long_format=True,
    )
    return _save(df, model_dir, "raw", "hbn.get_multiple_timeseries",
                 operation=operation, t_code=t_code, variable=variable,
                 activity=activity)


