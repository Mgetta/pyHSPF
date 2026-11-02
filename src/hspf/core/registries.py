from dataclasses import dataclass
from pathlib import Path
import pandas as pd
from hspf.core.units import Unit, UnitSpec, TimeBasis

REGISTRY_DIR = Path(__file__).parent.parent / "data" / "registries"




# 2. Pre-build ConstituentSpec lookup dictionary: (constituent, form) -> spec
@dataclass(frozen=True)
class ConstituentSpec:
    constituent: str
    numerator_form: str
    target_unit: UnitSpec
    multi_reach_policy: str
    denominator_constituent: str | None = None
    denominator_form: str | None = None

def _load_csv(filename: str) -> pd.DataFrame:
    return pd.read_csv(REGISTRY_DIR / filename, dtype=str, keep_default_na=False)

@dataclass(frozen=True)
class CatalogRegistry:
    catalog: pd.DataFrame
    constituents: pd.DataFrame
    forms: pd.DataFrame
    constituent_names: pd.DataFrame
#    constituent_aliases: pd.DataFrame
    units: pd.DataFrame
    reach_outputs: pd.DataFrame
    land_outputs: pd.DataFrame
    reach_inflows: pd.DataFrame
    constituent_specs: dict[tuple[str, str], ConstituentSpec]
    unit_specs: dict[str, UnitSpec]

def load_registry_tables():
    CONSTITUENTS = _load_csv("constituents.csv")
    CONSTITUENT_NAMES = _load_csv("constituent_names.csv")
#    CONSTITUENT_ALIASES = _load_csv("constituent_aliases.csv")
    UNITS = _load_csv("units.csv")
    REACH_OUTPUTS = _load_csv("reach_outputs.csv")
    LAND_OUTPUTS = _load_csv("land_outputs.csv")
    REACH_INFLOWS = _load_csv("reach_inflows.csv")
    CATALOG = _load_csv("catalog.csv")
    FORMS = _load_csv("forms.csv")

    # convert sub1 and sub2 to stripped strings. TODO: Store these in a databse and stop worrying about data types...
    CATALOG["sub1"] = CATALOG["sub1"].str.strip()
    CATALOG["sub2"] = CATALOG["sub2"].str.strip()

    REACH_OUTPUTS["sub1"] = REACH_OUTPUTS["sub1"].str.strip()
    REACH_OUTPUTS["sub2"] = REACH_OUTPUTS["sub2"].str.strip()
    LAND_OUTPUTS["sub1"] = LAND_OUTPUTS["sub1"].str.strip()
    LAND_OUTPUTS["sub2"] = LAND_OUTPUTS["sub2"].str.strip()
    REACH_INFLOWS["sub1"] = REACH_INFLOWS["sub1"].str.strip()
    REACH_INFLOWS["sub2"] = REACH_INFLOWS["sub2"].str.strip()

    CATALOG['is_total'] = CATALOG['is_total'].astype(bool)

    CATALOG['hbn_name'] = CATALOG['hbn_name'].str.strip()

    '''
    Load all registry tables from CSV files and return a CatalogRegistry instance.

    Returns:
        CatalogRegistry: A dataclass instance containing all loaded registry tables.
    '''
    #REACH_OUTPUTS: reach_outputs.csv $\bowtie$ catalog.csv $\bowtie$ constituents.csv (54 rows, 100% matched)


    CONSTITUENTS = CONSTITUENTS.merge(
        FORMS,
        on="form",
        how="left",
    )

    REACH_OUTPUTS = REACH_OUTPUTS.merge(
        CATALOG,
        on=["operation", "activity", "name", "sub1", "sub2"],
        how="left",
    ).merge(
        CONSTITUENTS[["constituent", "form", "units_default"]],
        on=["constituent", "form"],
        how="left",
    )

    LAND_OUTPUTS = LAND_OUTPUTS.merge(
        CATALOG,
        on=["operation", "activity", "name", "sub1", "sub2"],
        how="left",
    ).merge(
        CONSTITUENTS[["constituent", "form", "units_default"]],
        on=["constituent", "form"],
        how="left",
    )

    REACH_INFLOWS = REACH_INFLOWS.merge(
        CATALOG,
        on=["operation", "activity", "name", "sub1", "sub2"],
        how="left",
    ).merge(
        CONSTITUENTS[["constituent", "form", "units_default"]],
        on=["constituent", "form"],
        how="left",
    )


    #CATALOG = CATALOG.set_index(["operation", "activity", "name"])


    

    # 1. Pre-build UnitSpec lookup dictionary
    UNIT_SPECS: dict[str, UnitSpec] = {
        row["units_english"]: UnitSpec(
            code=row["units_english"],
            measure=Unit(row["measure"]) if row["measure"] else None,
            normalization=Unit(row["normalization"]) if row["normalization"] else None,
            interval=TimeBasis(row["interval"]) if row["interval"] else None,
            custom=row["custom"].lower() == "true",
            offset = float(row['offset'])
        )
        for _, row in UNITS.iterrows()
    }

    CONSTITUENT_SPECS: dict[tuple[str, str], ConstituentSpec] = {
    (row["constituent"], row["form"]): ConstituentSpec(
        constituent=row["constituent"],
        numerator_form=row["numerator_form"],
        denominator_constituent=row.get("denominator_constituent"),
        denominator_form=row.get("denominator_form"),
        target_unit=UNIT_SPECS[row["units_default"]],
        multi_reach_policy=row.get("multi_reach_policy", "sum") or "sum",
    )
    for _, row in CONSTITUENTS.iterrows()
}


    return CatalogRegistry(
        catalog=CATALOG,
        constituents=CONSTITUENTS,
        forms=FORMS,
        constituent_names=CONSTITUENT_NAMES,
#        constituent_aliases=CONSTITUENT_ALIASES,
        units=UNITS,
        reach_outputs=REACH_OUTPUTS,
        land_outputs=LAND_OUTPUTS,
        reach_inflows=REACH_INFLOWS,
        constituent_specs=CONSTITUENT_SPECS,
        unit_specs=UNIT_SPECS,
    )

CATALOG_REGISTRY = load_registry_tables()

# --- Public Query Helpers Used by Layer 3 ---
def query_boundary_table(table: str, constituent: str, form: str, catalog: CatalogRegistry = None, *, 
                     operation: str | None = None, 
                     pathway: str | list[str] | None = None, 
                     compartment: str | list[str] | None = None, 
                     carrier: str | list[str] | None = None, 
                     process: str | list[str] | None = None,
                     ) -> pd.DataFrame:

    if catalog is None:
        catalog = CATALOG_REGISTRY

    if table == "reach_outputs":
        table = catalog.reach_outputs.copy()
    elif table == "land_outputs":
        table = catalog.land_outputs.copy()
    elif table == "reach_inflows":
        table = catalog.reach_inflows.copy()
    else:
        raise ValueError(f"Unknown table: {table}")

    mask = (table["constituent"] == constituent) & \
           (table["form"] == form)

    optional_filters = {
        "operation": operation,
        "pathway": pathway,
        "compartment": compartment,
        "carrier": carrier,
        "process": process,
    }

    # if no optional filters are provided and an is_total row exists, return the is_total row
    if all(val is None for val in optional_filters.values()):
        is_total_mask = mask & (table["constituent_total"] == 'TRUE') #TODO use types...
        if table[is_total_mask].any(axis=None):
            table = table[is_total_mask]
    else:
        # 3. Dynamically update the mask for provided inputs
        for column, val in optional_filters.items():
            if val is not None:
                if isinstance(val, list):
                    mask &= table[column].isin(val)
                else:
                    mask &= (table[column] == val)


    table = table[mask]
    
    if table.empty:
        raise ValueError("No matching rows found for the given filters.")
    
    return table

def get_unit_spec(unit: str, interval: str | None = None) -> UnitSpec:
    """Retrieve the unit specification for a given unit string."""
    try:
        spec = CATALOG_REGISTRY.unit_specs[unit]
        if interval is not None:
            spec = UnitSpec(
                code=spec.code,
                measure=spec.measure,
                normalization=spec.normalization,
                interval=TimeBasis(interval),
                custom=spec.custom
            )
        return spec
    except KeyError:
        raise ValueError(f"Unknown unit specification for unit='{unit}'.")

def get_target_unit_spec(operation, activity, name, sub1, sub2):
    """Retrieve the target unit specification based on operation, activity, name, sub1, and sub2."""
    try:
        return CATALOG_REGISTRY.unit_specs[CATALOG_REGISTRY.catalog.query(f"operation == '{operation}' & activity == '{activity}' & name == '{name}' & sub1 == '{sub1}' & sub2 == '{sub2}'").iloc[0].units_english_y]
    except KeyError:
        raise ValueError(f"Unknown target unit specification for operation='{operation}', activity='{activity}', name='{name}', sub1='{sub1}', sub2='{sub2}'.")

def get_source_unit_spec(constituent: str, form: str) -> UnitSpec:
    """Retrieve the source unit specification for a given constituent and form."""
    try:
        return CATALOG_REGISTRY.unit_specs[CATALOG_REGISTRY.constituents.query(f"constituent == '{constituent}' & form == '{form}'").iloc[0].units_english]
    except KeyError:
        raise ValueError(f"Unknown source unit specification for constituent='{constituent}', form='{form}'.")

def resolve_constituent_key(name_or_alias: str) -> str:
    """Resolve any key, code, or pipe-delimited alias to canonical constituent key."""
    target = name_or_alias.strip().lower()
    for _, row in CATALOG_REGISTRY.constituent_names.iterrows():
        aliases = [a.strip().lower() for a in row.get("aliases", "").split("|") if a]
        if target in (row["key"].lower(), row["code"].lower(), *aliases):
            return row["key"]
    raise ValueError(f"Unknown constituent '{name_or_alias}'.")


def get_constituent_spec(constituent: str, form: str) -> ConstituentSpec:
    """Validate (constituent, form) and return its metadata spec."""
    try:
        return CATALOG_REGISTRY.constituent_specs[(constituent, form)]
    except KeyError:
        raise ValueError(f"Invalid constituent/form combination: ({constituent!r}, {form!r}).")


# def get_direct_terms(
#     constituent: str,
#     form: str,
#     operation: str | list[str] = "RCHRES",
#     fraction: str | None = None,
#     binding: str | None = None,
# ) -> pd.DataFrame:
#     """Query static members from direct_outputs ⋈ catalog."""
#     ops = [operation] if isinstance(operation, str) else list(operation)
#     df = DIRECT_TERMS[
#         (DIRECT_TERMS["constituent"] == constituent)
#         & (DIRECT_TERMS["form"] == form)
#         & (DIRECT_TERMS["operation"].isin(ops))
#     ]
#     if fraction is not None:
#         df = df[df["carrier"] == fraction]
#     if binding is not None:
#         df = df[df["binding"] == binding]
#     return df


# def get_inflow_terms(
#     constituent: str,
#     form: str = "load",
#     fraction: str | None = None,
#     binding: str | None = None,
# ) -> pd.DataFrame:
#     """Query RCHRES INFLOW target doors from inflow_targets ⋈ catalog."""
#     df = INFLOW_TERMS[
#         (INFLOW_TERMS["constituent"] == constituent)
#         & (INFLOW_TERMS["form"] == form)
#     ]
#     if fraction is not None:
#         df = df[df["carrier"] == fraction]
#     if binding is not None:
#         df = df[df["binding"] == binding]
#     return df