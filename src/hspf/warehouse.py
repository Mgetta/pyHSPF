import duckdb
from pathlib import Path
import pandas as pd

def init_hspf_db(db_path: str, reset: bool = False):
    """Initializes the HSPF model structure database."""
    db_path = Path(db_path)
    if reset and db_path.exists():
        db_path.unlink()

    with duckdb.connect(db_path.as_posix()) as con:
        # Create schema
        con.execute("CREATE SCHEMA IF NOT EXISTS hspf")
        
        # Create tables for HSPF model data
        create_hspf_model_hierarchy_tables(con)
        create_model_run_table(con)
        create_structure_tables(con)
        create_parameter_tables(con)
        create_timeseries_tables(con)

def load_df_to_table(con: duckdb.DuckDBPyConnection, df: pd.DataFrame, table_name: str, replace: bool = True):
    """
    Persist a pandas DataFrame into a DuckDB table. This will overwrite the table
    by default (replace=True).
    """
    if replace:
        con.execute(f"DROP TABLE IF EXISTS {table_name}")
    # register pandas DF and create table
    con.register("tmp_df", df)
    con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM tmp_df")
    con.unregister("tmp_df")


def create_hspf_model_hierarchy_tables(con: duckdb.DuckDBPyConnection):
    """
    Creates the tables that define the model -> version -> scenario -> run hierarchy.
    """
    con.execute('''
    CREATE SEQUENCE IF NOT EXISTS hspf.model_seq START 1;
    CREATE SEQUENCE IF NOT EXISTS hspf.model_version_seq START 1;
    CREATE SEQUENCE IF NOT EXISTS hspf.scenario_seq START 1;
    CREATE SEQUENCE IF NOT EXISTS hspf.model_run_seq START 1;

    -- Level 1: The overall Model (e.g., for a specific basin)
    CREATE TABLE IF NOT EXISTS hspf.models (
        model_pk        BIGINT PRIMARY KEY DEFAULT nextval('hspf.model_seq'),
        model_name      VARCHAR NOT NULL UNIQUE, -- e.g., 'Nemadji River Basin Model'
        description     VARCHAR
    );

    -- Level 2: A specific Version of a Model
    CREATE TABLE IF NOT EXISTS hspf.model_versions (
        model_version_pk BIGINT PRIMARY KEY DEFAULT nextval('hspf.model_version_seq'),
        model_pk         BIGINT NOT NULL REFERENCES hspf.models(model_pk),
        version_name     VARCHAR NOT NULL, -- e.g., 'v2.1', '2025_Update'
        release_date     DATE,
        description      VARCHAR,
        UNIQUE (model_pk, version_name)
    );

    -- Level 3: A Scenario within a Model Version
    CREATE TABLE IF NOT EXISTS hspf.scenarios (
        scenario_pk      BIGINT PRIMARY KEY DEFAULT nextval('hspf.scenario_seq'),
        model_version_pk BIGINT NOT NULL REFERENCES hspf.model_versions(model_version_pk),
        scenario_name    VARCHAR NOT NULL, -- e.g., 'Baseline_2020', 'Future_Climate_BMPs'
        description      VARCHAR,
        UNIQUE (model_version_pk, scenario_name)
    );

    -- Level 4: A single execution (Run) of a Scenario
    CREATE TABLE IF NOT EXISTS hspf.model_runs (
        model_run_pk   BIGINT PRIMARY KEY DEFAULT nextval('hspf.model_run_seq'),
        scenario_pk    BIGINT NOT NULL REFERENCES hspf.scenarios(scenario_pk),
        run_id         BIGINT,
        run_name       VARCHAR,          -- e.g., 'Run_1995-2015', 'Calibration_Run_A'
        start_year     INTEGER,
        end_year       INTEGER,
        run_timestamp  TIMESTAMP DEFAULT current_timestamp,
        notes          VARCHAR
    );
    ''')

def create_model_run_table(con: duckdb.DuckDBPyConnection):
    """
    Creates the table to store individual model runs linked to scenarios.
    """
    con.execute(
    '''
    CREATE SEQUENCE IF NOT EXISTS model_run_seq START 1;

    -- Table: hspf.model_runs
    -- Purpose: Stores individual model runs linked to scenarios.
    CREATE TABLE IF NOT EXISTS model_runs (
        model_run_pk   BIGINT PRIMARY KEY DEFAULT nextval('model_run_seq'),
        model_name     VARCHAR NOT NULL, -- e.g., 'Nemadji River Basin Model'
        run_id         BIGINT,
        run_name       VARCHAR,          -- e.g., 'Run_1995-2015', 'Calibration_Run_A'
        notes          VARCHAR
    );
    ''')

def insert_model_run(con: duckdb.DuckDBPyConnection, model_name: str, run_id: int, run_name: str = None, notes: str = None):
    """
    Inserts a new model run into the model_runs table.
    """
    con.execute(
        '''
        INSERT INTO model_runs (model_name, run_id, run_name, notes)
        VALUES (?, ?, ?, ?)
        ''',
        (model_name, run_id, run_name, notes)
    )

def create_structure_tables(con: duckdb.DuckDBPyConnection):
    """
    Creates tables that define the structural components of an HSPF model,
    linking them to a core model definition.
    """
    con.execute(
    '''
    CREATE SEQUENCE IF NOT EXISTS hspf.operation_seq START 1;
    CREATE SEQUENCE IF NOT EXISTS hspf.catchment_seq START 1;

    -- Table: hspf.operations
    -- Purpose: Registry of all land segments and reaches (e.g., PERLND, RCHRES).
    CREATE TABLE IF NOT EXISTS hspf.operations (
        operation_pk     BIGINT PRIMARY KEY DEFAULT nextval('hspf.operation_seq'),
        model_pk         BIGINT NOT NULL REFERENCES hspf.models(model_pk),
        operation_id     INTEGER NOT NULL,       -- e.g., The PERLND number (101)
        operation_type   VARCHAR NOT NULL,       -- e.g., 'PERLND', 'RCHRES'
        UNIQUE (model_pk, operation_id, operation_type)
    );


    -- Table: hspf.catchments
    -- Purpose: Defines the subwatersheds or catchments in the model.
    CREATE TABLE IF NOT EXISTS hspf.catchments (
        catchment_pk      BIGINT PRIMARY KEY DEFAULT nextval('hspf.catchment_seq'),
        model_pk          BIGINT NOT NULL REFERENCES hspf.models(model_pk),
        catchment_id      INTEGER NOT NULL,
        catchment_name    VARCHAR,
        UNIQUE (model_pk, catchment_id)
    );

    -- Table: hspf.catchment_operations
    -- Purpose: Maps operations (land segments) to catchments, defining the model's spatial structure and connectivity.
    CREATE TABLE IF NOT EXISTS hspf.catchment_operations (
        catchment_pk          BIGINT REFERENCES hspf.catchments(catchment_pk),
        source_operation_pk   BIGINT REFERENCES hspf.operations(operation_pk),
        target_operation_pk   BIGINT REFERENCES hspf.operations(operation_pk),
        model_pk              BIGINT NOT NULL REFERENCES hspf.models(model_pk),
        value                 FLOAT,
        mlno                  INTEGER, -- Mass-link number from SCHEMATIC block
        tmemsb1               INTEGER, -- Mass-link memory storage 1
        tmemsb2               INTEGER  -- Mass-link memory storage 2
    );
    ''')


def create_parameter_tables(con: duckdb.DuckDBPyConnection):
    """
    Creates tables to store the parameters, flags, and properties for model operations,
    linking them to the model structure.
    """
    con.execute(
    '''
    CREATE SEQUENCE IF NOT EXISTS hspf.parameter_seq START 1;
    CREATE SEQUENCE IF NOT EXISTS hspf.flag_seq START 1;
    CREATE SEQUENCE IF NOT EXISTS hspf.property_seq START 1;

    -- Table: hspf.parameters
    -- Purpose: Stores numeric model parameters for each operation (e.g., LZSN, UZSN).
    CREATE TABLE IF NOT EXISTS hspf.parameters (
        parameter_pk      BIGINT PRIMARY KEY DEFAULT nextval('hspf.parameter_seq'),
        operation_pk      BIGINT NOT NULL REFERENCES hspf.operations(operation_pk),
        parameter_name    VARCHAR,
        parameter_value   FLOAT
    );

    -- Table: hspf.flags
    -- Purpose: Stores integer-based flags for model operations (e.g., snow flags).
    CREATE TABLE IF NOT EXISTS hspf.flags (
        flag_pk           BIGINT PRIMARY KEY DEFAULT nextval('hspf.flag_seq'),
        operation_pk      BIGINT NOT NULL REFERENCES hspf.operations(operation_pk),
        flag_name         VARCHAR,
        flag_value        INTEGER
    );

    -- Table: hspf.properties
    -- Purpose: Stores string-based properties for model operations (e.g., land use names).
    CREATE TABLE IF NOT EXISTS hspf.properties (
        property_pk       BIGINT PRIMARY KEY DEFAULT nextval('hspf.property_seq'),
        operation_pk      BIGINT NOT NULL REFERENCES hspf.operations(operation_pk),
        property_name     VARCHAR,
        property_value    VARCHAR
    );
    ''')


def create_timeseries_tables(con: duckdb.DuckDBPyConnection):
    """
    Creates tables for storing model output timeseries, linking them to a specific model run.
    Note: Simplified schema without foreign keys to avoid cross-schema issues.
    """
    con.execute(
    '''
    CREATE SEQUENCE IF NOT EXISTS timeseries_metadata_seq START 1;

    -- Table: hspf.timeseries_metadata
    -- Purpose: Metadata for each unique timeseries produced by a model run.
    CREATE TABLE IF NOT EXISTS hspf.timeseries_metadata (
        timeseries_pk     BIGINT PRIMARY KEY DEFAULT nextval('timeseries_metadata_seq'),
        model_run_pk      BIGINT NOT NULL,  -- References model_runs(model_run_pk)
        operation_id      INTEGER,           -- Operation ID (e.g., PERLND number)
        operation_type    VARCHAR,           -- e.g., 'PERLND', 'RCHRES'
        ts_name           VARCHAR NOT NULL,  -- e.g., 'ROVOL','SOSED'
        activity          VARCHAR,           -- e.g., 'SEDTRN','HYDR'
        timestep          VARCHAR,           -- e.g., 'hourly','daily'
        unit              VARCHAR,           -- e.g., 'cfs','mg/L'
        timeseries_type   VARCHAR            -- e.g., 'cumulative', 'instantaneous'
    );

    -- Table: hspf.timeseries
    -- Purpose: Stores the actual timeseries data points in a narrow/long format.
    CREATE TABLE IF NOT EXISTS hspf.timeseries (
        timeseries_pk BIGINT NOT NULL,  -- References hspf.timeseries_metadata(timeseries_pk)
        datetime      TIMESTAMP NOT NULL,
        value         DOUBLE,
        UNIQUE(timeseries_pk, datetime)
    );
    ''')

def connect(db_path: str, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(database=db_path.as_posix(), read_only=read_only)

def insert_df_into_table(con: duckdb.DuckDBPyConnection, df: pd.DataFrame, table_name: str, schema: str = 'hspf', clear_before_insert: bool = True):
    """
    Inserts a pandas DataFrame into an existing table in a specified schema,
    matching columns by name, making the operation robust to column order.

    Args:
        con: The DuckDB connection object.
        df: The pandas DataFrame to insert.
        table_name: The name of the target table.
        schema: The schema of the target table (e.g., 'hspf', 'analytics').
        clear_before_insert: If True, deletes all rows from the table before insertion.
    """
    target_table = f"{schema}.{table_name}"
    
    if not df.empty:
        if clear_before_insert:
            print(f"  Clearing all data from {target_table}...")
            con.execute(f"DELETE FROM {target_table}")

        # Get column names from the DataFrame and format them for the SQL query.
        # Quoting column names handles special characters, spaces, and case-sensitivity.
        cols = df.columns
        col_string = ", ".join([f'"{c}"' for c in cols])
        
        # Register the DataFrame as a temporary view so we can query it
        temp_view_name = "temp_df_to_insert"
        con.register(temp_view_name, df)

        print(f"  Inserting {len(df)} rows into {target_table}...")
        
        # The SQL statement is now robust to column order in the DataFrame
        sql = f"INSERT INTO {target_table} ({col_string}) SELECT {col_string} FROM {temp_view_name}"
        con.execute(sql)

        # Clean up the temporary view
        con.unregister(temp_view_name)
    else:
        print(f"  DataFrame is empty. Skipping insertion into {target_table}.")


class OutputWarehouse:
    """
    A loosely coupled class for managing HSPF model outputs in a warehouse.
    
    This class follows composition over inheritance and provides methods to:
    - Store model run outputs
    - Query stored outputs
    - Manage multiple models and scenarios
    
    Example:
        warehouse = OutputWarehouse("/path/to/warehouse.duckdb")
        warehouse.store_model_run("MyModel", "v1.0", "Baseline", run_data)
        results = warehouse.query_timeseries("MyModel", "v1.0", "Baseline")
    """
    
    def __init__(self, db_path: str, initialize: bool = True):
        """
        Initialize the output warehouse.
        
        Args:
            db_path: Path to the DuckDB database file
            initialize: If True, creates tables if they don't exist
        """
        self.db_path = Path(db_path)
        if initialize:
            self._initialize_schema()
    
    def _initialize_schema(self):
        """Initialize database schema if it doesn't exist."""
        init_hspf_db(str(self.db_path), reset=False)
    
    def get_connection(self, read_only: bool = False):
        """
        Get a connection to the warehouse database.
        
        Args:
            read_only: If True, opens in read-only mode
            
        Returns:
            DuckDB connection context manager
        """
        return connect(str(self.db_path), read_only=read_only)
    
    def store_model_run(self, model_name: str, run_id: int, 
                       run_name: str = None, notes: str = None):
        """
        Register a new model run in the warehouse.
        
        Args:
            model_name: Name of the model
            run_id: Unique identifier for this run
            run_name: Optional descriptive name
            notes: Optional notes about this run
            
        Returns:
            model_run_pk: Primary key of the inserted run
        """
        with self.get_connection() as con:
            insert_model_run(con, model_name, run_id, run_name, notes)
            # Get the PK of the inserted run
            result = con.execute(
                "SELECT model_run_pk FROM model_runs WHERE model_name = ? AND run_id = ? ORDER BY model_run_pk DESC LIMIT 1",
                (model_name, run_id)
            ).fetchone()
            return result[0] if result else None
    
    def store_timeseries_data(self, df: pd.DataFrame, clear_before: bool = False):
        """
        Store timeseries data in the warehouse.
        
        Args:
            df: DataFrame with timeseries data
            clear_before: If True, clears existing data before insertion
        """
        with self.get_connection() as con:
            insert_df_into_table(con, df, 'timeseries', schema='hspf', 
                               clear_before_insert=clear_before)
    
    def query_timeseries(self, model_name: str = None, run_id: int = None,
                        operation_type: str = None, ts_name: str = None) -> pd.DataFrame:
        """
        Query timeseries data from the warehouse.
        
        Args:
            model_name: Optional filter by model name
            run_id: Optional filter by run ID
            operation_type: Optional filter by operation type (e.g., 'PERLND', 'RCHRES')
            ts_name: Optional filter by timeseries name
            
        Returns:
            DataFrame with filtered timeseries data
        """
        query = """
            SELECT 
                mr.model_name,
                mr.run_id,
                mr.run_name,
                tm.ts_name,
                tm.activity,
                tm.timestep,
                tm.unit,
                ts.datetime,
                ts.value
            FROM hspf.timeseries ts
            JOIN hspf.timeseries_metadata tm ON ts.timeseries_pk = tm.timeseries_pk
            JOIN model_runs mr ON tm.model_run_pk = mr.model_run_pk
            WHERE 1=1
        """
        
        params = []
        if model_name:
            query += " AND mr.model_name = ?"
            params.append(model_name)
        if run_id is not None:
            query += " AND mr.run_id = ?"
            params.append(run_id)
        if ts_name:
            query += " AND tm.ts_name = ?"
            params.append(ts_name)
            
        with self.get_connection(read_only=True) as con:
            return con.execute(query, params).df()
    
    def list_models(self) -> pd.DataFrame:
        """
        List all models in the warehouse.
        
        Returns:
            DataFrame with model information
        """
        query = """
            SELECT DISTINCT model_name, COUNT(DISTINCT run_id) as num_runs
            FROM model_runs
            GROUP BY model_name
            ORDER BY model_name
        """
        with self.get_connection(read_only=True) as con:
            return con.execute(query).df()
    
    def list_runs(self, model_name: str = None) -> pd.DataFrame:
        """
        List all runs for a model.
        
        Args:
            model_name: Optional model name to filter by
            
        Returns:
            DataFrame with run information
        """
        query = "SELECT * FROM model_runs"
        params = []
        
        if model_name:
            query += " WHERE model_name = ?"
            params.append(model_name)
            
        query += " ORDER BY model_name, run_id"
        
        with self.get_connection(read_only=True) as con:
            return con.execute(query, params).df()
    
    def export_run_data(self, model_name: str, run_id: int, 
                       output_path: str, format: str = 'parquet'):
        """
        Export data for a specific run to a file.
        
        Args:
            model_name: Name of the model
            run_id: Run identifier
            output_path: Path where to save the export
            format: Export format ('parquet', 'csv', 'json')
        """
        df = self.query_timeseries(model_name=model_name, run_id=run_id)
        
        output_path = Path(output_path)
        if format == 'parquet':
            df.to_parquet(output_path)
        elif format == 'csv':
            df.to_csv(output_path, index=False)
        elif format == 'json':
            df.to_json(output_path, orient='records')
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        return len(df)