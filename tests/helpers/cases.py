from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import pandas as pd


def slugify(value: object) -> str:
    """Make a value safe for use in a golden filename."""
    if isinstance(value, (list, tuple, set)):
        value = "-".join(str(item) for item in value)
    text = str(value).strip().replace(" ", "-")
    text = re.sub(r"[^A-Za-z0-9_.=-]+", "-", text)
    return text.strip("-").lower() or "na"


def golden_slug(function_name: str, **context: object) -> str:
    """Return the deterministic filename stem for a golden case."""
    stem = slugify(function_name)
    for key, value in context.items():
        stem += f"__{slugify(key)}={slugify(value)}"
    return stem


@dataclass(frozen=True)
class Case:
    """A pure-data description of one golden output."""

    model_name: str
    group: str
    name: str
    kwargs: Dict[str, Any]
    sort_by: Optional[Tuple[str, ...]] = None
    label: Optional[str] = None

    @property
    def slug(self) -> str:
        """Deterministic filename stem for this case."""
        return golden_slug(self.name, **self.kwargs)

    @property
    def filename(self) -> str:
        """Parquet filename for this case's golden output."""
        return f"{self.slug}.parquet"


def _catchment_loading(model, constituent: str, simulation_period: str = "yearly"):
    return model.reports.catchment_loading(
        constituent=constituent,
        simulation_period=simulation_period,
    )


def _watershed_loading(
    model,
    constituent: str,
    reach_ids,
    upstream_reach_ids=None,
    by_landcover: bool = False,
    simulation_period: str = "yearly",
):
    return model.reports.watershed_loading(
        constituent=constituent,
        reach_ids=reach_ids,
        upstream_reach_ids=upstream_reach_ids,
        by_landcover=by_landcover,
        simulation_period=simulation_period,
    )


def _total_contributions(model, constituent: str, target_reach_id: int):
    return model.reports.total_contributions(constituent, target_reach_id)


def _catchment_contributions(model, constituent: str, target_reach_id: int):
    return model.reports.catchment_contributions(constituent, target_reach_id)


def _total_phosphorus(model, operation: str = "PERLND", t_code: int = 4):
    from hspf.reports.nutrients import total_phosphorus

    return total_phosphorus(model.uci, model.hbns, t_code=t_code, operation=operation)


def _total_nitrogen(model, operation: str = "PERLND", t_code: int = 4):
    from hspf.reports.nutrients import total_nitrogen

    return total_nitrogen(model.uci, model.hbns, t_code=t_code, operation=operation)


def _subwatersheds(model):
    return model.uci.network.subwatersheds().reset_index()


def _outlets(model):
    return pd.DataFrame({"reach_id": sorted(model.uci.network.outlets())})


def _upstream_network(model, reach_id: int):
    reaches = model.uci.network._upstream(reach_id)
    return pd.DataFrame({"reach_id": sorted(reaches)})


def _watershed_area(model, reach_ids, upstream_reach_ids=None):
    area = model.uci.network.drainage_area(reach_ids, upstream_reach_ids)
    return pd.DataFrame({"drainage_area": [area]})


def _drainage_area_landcover(model, reach_ids, upstream_reach_ids=None):
    return model.uci.network.drainage_area_landcover(
        reach_ids,
        upstream_reach_ids,
    ).reset_index()


def _get_opnids(model, operation: str, reach_ids, upstream_reach_ids=None):
    opnids = model.uci.network.get_opnids(operation, reach_ids, upstream_reach_ids)
    return pd.DataFrame({"OPNID": sorted(opnids)})


def _calibration_order(model, reach_ids):
    order = model.uci.network.calibration_order(reach_ids)
    rows = [
        {"order": position, "reach_id": reach_id}
        for position, group in enumerate(order)
        for reach_id in sorted(group)
    ]
    return pd.DataFrame(rows)


def _raw_timeseries(model, operation: str, t_code: int, variable: str, activity=None):
    return model.hbns.get_multiple_timeseries(
        operation,
        t_code,
        variable,
        activity=activity,
        long_format=True,
    )


COMPUTE_REGISTRY: Dict[str, Callable[..., pd.DataFrame]] = {
    "reports.catchment_loading": _catchment_loading,
    "reports.watershed_loading": _watershed_loading,
    "reports.total_contributions": _total_contributions,
    "reports.catchment_contributions": _catchment_contributions,
    "nutrients.total_phosphorus": _total_phosphorus,
    "nutrients.total_nitrogen": _total_nitrogen,
    "network.subwatersheds": _subwatersheds,
    "network.outlets": _outlets,
    "network.upstream_network": _upstream_network,
    "network.drainage_area": _watershed_area,
    "network.drainage_area_landcover": _drainage_area_landcover,
    "network.get_opnids": _get_opnids,
    "network.calibration_order": _calibration_order,
    "hbn.get_multiple_timeseries": _raw_timeseries,
}


def compute_case(model, case: Case) -> pd.DataFrame:
    """Run the compute function for one golden case."""
    try:
        compute = COMPUTE_REGISTRY[case.name]
    except KeyError:
        available = ", ".join(sorted(COMPUTE_REGISTRY))
        raise KeyError(f"No compute function registered for {case.name}. Available: {available}")
    return compute(model, **case.kwargs)


def cases(config) -> List[Case]:
    """Return every golden case for one model config.

    This function is the single source of truth for what goldens should exist.
    It should not load the model or inspect UCI/HBN files.
    """
    model_name = config.model_name
    result: List[Case] = []

    # Catchment Loading Cases
    for constituent in config.LOADING_CONSTITUENTS:
        result.append(
            Case(
                model_name=model_name,
                group="reports",
                name="reports.catchment_loading",
                kwargs={"constituent": constituent, "simulation_period": "yearly"},
            )
        )

    # Watershed Loading Cases
    for constituent in config.LOADING_CONSTITUENTS:
        for watershed in config.WATERSHEDS:
            for by_landcover in (False, True):
                result.append(
                    Case(
                        model_name=model_name,
                        group="reports",
                        name="reports.watershed_loading",
                        kwargs={
                            "constituent": constituent,
                            "reach_ids": watershed["reach_ids"],
                            "upstream_reach_ids": watershed.get("upstream_reach_ids"),
                            "by_landcover": by_landcover,
                            "simulation_period": "yearly",
                        },
                        label=watershed.get("label"),
                    )
                )

    # Contribution Cases
    for constituent in config.CONTRIBUTION_CONSTITUENTS:
        for target_reach_id in config.TARGET_REACH_IDS:
            result.append(
                Case(
                    model_name=model_name,
                    group="reports",
                    name="reports.total_contributions",
                    kwargs={
                        "constituent": constituent,
                        "target_reach_id": target_reach_id,
                    },
                )
            )
            result.append(
                Case(
                    model_name=model_name,
                    group="reports",
                    name="reports.catchment_contributions",
                    kwargs={
                        "constituent": constituent,
                        "target_reach_id": target_reach_id,
                    },
                )
            )

    # Total Phosphorus / Total Nitrogen Cases
    for operation in config.RECIPE_OPERATIONS:
        for t_code in config.RECIPE_T_CODES:
            result.append(
                Case(
                    model_name=model_name,
                    group="recipes",
                    name="nutrients.total_phosphorus",
                    kwargs={"operation": operation, "t_code": t_code},
                )
            )
            result.append(
                Case(
                    model_name=model_name,
                    group="recipes",
                    name="nutrients.total_nitrogen",
                    kwargs={"operation": operation, "t_code": t_code},
                )
            )

    # Network Cases
    result.append(
        Case(
            model_name=model_name,
            group="network",
            name="network.subwatersheds",
            kwargs={},
        )
    )
    result.append(
        Case(
            model_name=model_name,
            group="network",
            name="network.outlets",
            kwargs={},
        )
    )

    for reach_id in config.TARGET_REACH_IDS:
        result.append(
            Case(
                model_name=model_name,
                group="network",
                name="network.upstream_network",
                kwargs={"reach_id": reach_id},
            )
        )

    for watershed in config.WATERSHEDS:
        watershed_kwargs = {
            "reach_ids": watershed["reach_ids"],
            "upstream_reach_ids": watershed.get("upstream_reach_ids"),
        }
        result.append(
            Case(
                model_name=model_name,
                group="network",
                name="network.drainage_area",
                kwargs=dict(watershed_kwargs),
                label=watershed.get("label"),
            )
        )
        result.append(
            Case(
                model_name=model_name,
                group="network",
                name="network.drainage_area_landcover",
                kwargs=dict(watershed_kwargs),
                label=watershed.get("label"),
            )
        )

        for operation in config.GET_OPNID_OPERATIONS:
            result.append(
                Case(
                    model_name=model_name,
                    group="network",
                    name="network.get_opnids",
                    kwargs={"operation": operation, **watershed_kwargs},
                    label=watershed.get("label"),
                )
            )

    for reach_ids in getattr(config, "CALIBRATION_REACH_IDS", ()):
        result.append(
            Case(
                model_name=model_name,
                group="network",
                name="network.calibration_order",
                kwargs={"reach_ids": reach_ids},
            )
        )

    # Raw Timeseries Cases
    for spec in config.RAW_TIMESERIES:
        result.append(
            Case(
                model_name=model_name,
                group="raw",
                name="hbn.get_multiple_timeseries",
                kwargs={
                    "operation": spec["operation"],
                    "t_code": spec["t_code"],
                    "variable": spec["variable"],
                    "activity": spec.get("activity"),
                },
            )
        )

    return result


def all_cases(configs: Iterable[object]) -> List[Case]:
    """Return the flattened case list for many configs."""
    return [case for config in configs for case in cases(config)]


def case_id(case: Case) -> str:
    """Readable pytest id / console label for one case."""
    parts = [case.model_name, case.group, case.name]
    if case.label:
        parts.append(case.label)
    parts.extend(f"{key}={value}" for key, value in case.kwargs.items())
    return "::".join(str(part) for part in parts)
