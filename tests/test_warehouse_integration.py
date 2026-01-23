"""
Tests for warehouse integration with hspfModel.
"""
import tempfile
from pathlib import Path
from hspf import ModelOutputPersister


def test_persister_init():
    """Test persister initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        persister = ModelOutputPersister(str(db_path))
        
        warehouse = persister.get_warehouse()
        assert warehouse is not None
        assert db_path.exists()


def test_persister_basic_run_storage():
    """Test basic run storage through persister."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.duckdb"
        persister = ModelOutputPersister(str(db_path))
        
        # Mock model object (in real usage this would be an hspfModel)
        class MockModel:
            pass
        
        model = MockModel()
        
        # Store a run (without actual data extraction)
        run_pk = persister.persist_model_run(
            model=model,
            model_name="Test Model",
            run_id=1,
            run_name="Test Run",
            notes="Integration test"
        )
        
        assert run_pk is not None
        
        # Verify it was stored
        warehouse = persister.get_warehouse()
        runs = warehouse.list_runs(model_name="Test Model")
        assert len(runs) == 1
        assert runs.iloc[0]['run_name'] == "Test Run"


if __name__ == "__main__":
    test_persister_init()
    test_persister_basic_run_storage()
    print("All integration tests passed!")
