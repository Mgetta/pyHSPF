from hspf.lake.catalogs.entities import ENTITIES_COLUMNS, ENTITIES_CATALOG_NAME
from hspf.lake.catalogs.edges import EDGES_COLUMNS, EDGES_CATALOG_NAME
from hspf.lake.catalogs.runs import RUNS_COLUMNS, RUNS_CATALOG_NAME
from hspf.lake.catalogs.mass_links import MASS_LINKS_COLUMNS, MASS_LINKS_CATALOG_NAME
from hspf.lake.catalogs.io import (
    append_catalog_rows,
    read_catalog_table,
    write_catalog_table,
)
from hspf.lake.layout import LakeLayout
from pathlib import Path
from typing import Iterable
import pandas as pd


CATALOGS = {
    "runs": {
        "name": RUNS_CATALOG_NAME,
        "columns": RUNS_COLUMNS,
        "label": "Run"
    },
    "entities": {
        "name": ENTITIES_CATALOG_NAME,
        "columns": ENTITIES_COLUMNS,
        "label": "Entity"
    },
    "edges": {
        "name": EDGES_CATALOG_NAME,
        "columns": EDGES_COLUMNS,
        "label": "Edge"
    },
    "mass_links": {
        "name": MASS_LINKS_CATALOG_NAME,
        "columns": MASS_LINKS_COLUMNS,
        "label": "Mass Link"
    },
}


def write_catalog(catalog_name, layout: LakeLayout, records: Iterable | pd.DataFrame, *, overwrite: bool = True) -> Path:
    return write_catalog_table(
        layout,
        CATALOGS[catalog_name]["name"],
        records,
        CATALOGS[catalog_name]["columns"],
        overwrite=overwrite,
        label=CATALOGS[catalog_name]["label"],
    )

def append_catalog(catalog_name, layout: LakeLayout, records: Iterable | pd.DataFrame, *, replace_existing: bool = False) -> Path:
    return append_catalog_rows(
        layout,
        CATALOGS[catalog_name]["name"],
        records,
        CATALOGS[catalog_name]["columns"],
        replace_existing=replace_existing,
        label=CATALOGS[catalog_name]["label"],
    )

def read_catalog(catalog_name, layout: LakeLayout) -> pd.DataFrame:
    return read_catalog_table(
        layout,
        CATALOGS[catalog_name]["name"],
        CATALOGS[catalog_name]["columns"],
    )