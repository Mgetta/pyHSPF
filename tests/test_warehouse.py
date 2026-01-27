"""
Tests for the OutputWarehouse functionality.
"""
import tempfile
import pandas as pd
from pathlib import Path
from hspf.warehouse import OutputWarehouse, init_hspf_db


def test_init_warehouse():
    """Test warehouse initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        warehouse = OutputWarehouse(str(db_path))
        assert db_path.exists()


def test_store_model_run():
    """Test storing a model run."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        warehouse = OutputWarehouse(str(db_path))
        
        run_pk = warehouse.store_model_run(
            model_name="TestModel",
            run_id=1,
            run_name="Initial Run",
            notes="Test run"
        )
        
        assert run_pk is not None
        
        # Verify the run was stored
        runs = warehouse.list_runs(model_name="TestModel")
        assert len(runs) == 1
        assert runs.iloc[0]['model_name'] == "TestModel"
        assert runs.iloc[0]['run_id'] == 1


def test_list_models():
    """Test listing models."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        warehouse = OutputWarehouse(str(db_path))
        
        # Store runs for multiple models
        warehouse.store_model_run("Model1", 1)
        warehouse.store_model_run("Model1", 2)
        warehouse.store_model_run("Model2", 1)
        
        models = warehouse.list_models()
        assert len(models) == 2
        
        model1 = models[models['model_name'] == 'Model1']
        assert model1.iloc[0]['num_runs'] == 2
        
        model2 = models[models['model_name'] == 'Model2']
        assert model2.iloc[0]['num_runs'] == 1


def test_export_run_data():
    """Test exporting run data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        warehouse = OutputWarehouse(str(db_path))
        
        # Store a model run
        warehouse.store_model_run("TestModel", 1)
        
        # Export (will be empty but should not error)
        export_path = Path(tmpdir) / "export.csv"
        count = warehouse.export_run_data("TestModel", 1, str(export_path), format='csv')
        
        assert export_path.exists()
        assert count == 0  # No timeseries data yet


def test_store_timeseries_metadata():
    """Test storing timeseries metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        warehouse = OutputWarehouse(str(db_path))
        
        # Store a model run
        run_pk = warehouse.store_model_run("TestModel", 1)
        
        # Store timeseries metadata
        ts_pk = warehouse.store_timeseries_metadata(
            model_run_pk=run_pk,
            ts_name="ROVOL",
            operation_id=101,
            operation_type="RCHRES",
            activity="HYDR",
            timestep="daily",
            unit="cfs",
            timeseries_type="instantaneous"
        )
        
        assert ts_pk is not None
        
        # Verify metadata was stored
        with warehouse.get_connection(read_only=True) as con:
            result = con.execute(
                "SELECT * FROM hspf.timeseries_metadata WHERE timeseries_pk = ?",
                (ts_pk,)
            ).fetchone()
            
            assert result is not None
            assert result[2] == 101  # operation_id
            assert result[3] == "RCHRES"  # operation_type
            assert result[4] == "ROVOL"  # ts_name


def test_store_timeseries_complete():
    """Test storing both metadata and timeseries data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        warehouse = OutputWarehouse(str(db_path))
        
        # Store a model run
        run_pk = warehouse.store_model_run("TestModel", 1)
        
        # Create sample timeseries data
        dates = pd.date_range(start='2020-01-01', periods=5, freq='D')
        df = pd.DataFrame({
            'datetime': dates,
            'value': [100.5, 105.2, 98.3, 103.7, 110.1]
        })
        
        # Store both metadata and data
        ts_pk = warehouse.store_timeseries(
            model_run_pk=run_pk,
            ts_name="ROVOL",
            df=df,
            operation_id=101,
            operation_type="RCHRES",
            activity="HYDR",
            timestep="daily",
            unit="cfs"
        )
        
        assert ts_pk is not None
        
        # Query the stored timeseries
        result = warehouse.query_timeseries(model_name="TestModel", ts_name="ROVOL")
        
        assert len(result) == 5
        assert result.iloc[0]['ts_name'] == "ROVOL"
        assert result.iloc[0]['unit'] == "cfs"


if __name__ == "__main__":
    test_init_warehouse()
    test_store_model_run()
    test_list_models()
    test_export_run_data()
    test_store_timeseries_metadata()
    test_store_timeseries_complete()
    print("All tests passed!")
