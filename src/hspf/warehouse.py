import duckdb
from pathlib import Path
import pandas as pd

_SQL_SCHEMA = Path(__file__).parent.parent.parent / 'sql' / 'schema.sql'


def init_hspf_db(db_path: str, reset: bool = False):
    """Initializes the HSPF model structure database using sql/schema.sql."""
    db_path = Path(db_path)
    if reset and db_path.exists():
        db_path.unlink()

    schema_sql = _SQL_SCHEMA.read_text()

    with duckdb.connect(db_path.as_posix()) as con:
        for statement in schema_sql.split(';'):
            stmt = statement.strip()
            if stmt:
                con.execute(stmt)


def connect(db_path: str, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(database=db_path.as_posix(), read_only=read_only)


def load_df_to_table(con: duckdb.DuckDBPyConnection, df: pd.DataFrame, table_name: str, replace: bool = True):
    """
    Persist a pandas DataFrame into a DuckDB table. This will overwrite the table
    by default (replace=True).
    """
    if replace:
        con.execute(f"DROP TABLE IF EXISTS {table_name}")
    con.register("tmp_df", df)
    con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM tmp_df")
    con.unregister("tmp_df")


def get_column_names(con: duckdb.DuckDBPyConnection, table_schema: str, table_name: str) -> list:
    """
    Get the column names of a DuckDB table.

    Parameters
    ----------
    table_schema : str
        The schema containing the table (e.g., 'uci', 'output', 'main').
    table_name : str
        The table name without schema prefix (e.g., 'operations', 'models').
    """
    query = """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = ? AND table_schema = ?
    """
    result = con.execute(query, [table_name, table_schema]).fetchall()
    column_names = [row[0] for row in result]
    return column_names


def add_df_to_table(con: duckdb.DuckDBPyConnection, df: pd.DataFrame, table_schema: str, table_name: str):
    """
    Append a pandas DataFrame into a DuckDB table. This will create the table
    if it does not exist.
    """
    existing_columns = get_column_names(con, table_schema, table_name)
    df = df[existing_columns]

    con.register("tmp_df", df)
    con.execute(f"""
        INSERT INTO {table_schema}.{table_name}
        SELECT * FROM tmp_df
    """)
    con.unregister("tmp_df")


def insert_df_into_table(con: duckdb.DuckDBPyConnection, df: pd.DataFrame, table_name: str, schema: str = 'uci', clear_before_insert: bool = True):
    """
    Inserts a pandas DataFrame into an existing table in a specified schema,
    matching columns by name, making the operation robust to column order.

    Args:
        con: The DuckDB connection object.
        df: The pandas DataFrame to insert.
        table_name: The name of the target table.
        schema: The schema of the target table (e.g., 'uci', 'output', 'reports').
        clear_before_insert: If True, deletes all rows from the table before insertion.
    """
    target_table = f"{schema}.{table_name}"

    if not df.empty:
        if clear_before_insert:
            con.execute(f"DELETE FROM {target_table}")

        cols = df.columns
        col_string = ", ".join([f'"{c}"' for c in cols])

        temp_view_name = "temp_df_to_insert"
        con.register(temp_view_name, df)

        sql = f"INSERT INTO {target_table} ({col_string}) SELECT {col_string} FROM {temp_view_name}"
        con.execute(sql)

        con.unregister(temp_view_name)


def drop_model_data(con: duckdb.DuckDBPyConnection, model_name: str):
    """
    Deletes all rows related to a specific model across all warehouse tables.
    """
    tables = [
        ('main', 'models'),
        ('uci', 'operations'),
        ('uci', 'schematics'),
        ('uci', 'masslinks'),
        ('uci', 'extsources'),
        ('uci', 'exttargets'),
        ('uci', 'networks'),
        ('uci', 'ftables'),
        ('uci', 'parameters'),
        ('uci', 'flags'),
        ('uci', 'properties'),
        ('output', 'timeseries'),
        ('reports', 'catchment_loading'),
    ]
    for schema, table in tables:
        qualified = f"{schema}.{table}" if schema != 'main' else table
        try:
            con.execute(f"DELETE FROM {qualified} WHERE model_name = ?", [model_name])
        except Exception:
            pass
