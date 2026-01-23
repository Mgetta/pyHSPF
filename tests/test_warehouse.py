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


if __name__ == "__main__":
    test_init_warehouse()
    test_store_model_run()
    test_list_models()
    test_export_run_data()
    print("All tests passed!")
