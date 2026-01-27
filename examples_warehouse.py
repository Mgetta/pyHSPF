"""
Example usage of the OutputWarehouse for storing and querying HSPF model outputs.

This demonstrates the loosely coupled design where the warehouse can be used
independently for storing outputs from multiple models and scenarios.
"""

import pandas as pd
from datetime import datetime, timedelta
from hspf import OutputWarehouse


def example_basic_usage():
    """Basic usage example."""
    print("=== Basic OutputWarehouse Usage ===\n")
    
    # Initialize the warehouse
    warehouse = OutputWarehouse("example_warehouse.duckdb")
    
    # Store a model run
    print("Storing model runs...")
    warehouse.store_model_run(
        model_name="Nemadji River Basin",
        run_id=1,
        run_name="Baseline Calibration",
        notes="Initial calibration run for 2010-2020"
    )
    
    warehouse.store_model_run(
        model_name="Nemadji River Basin",
        run_id=2,
        run_name="Climate Scenario A",
        notes="Future climate projection scenario"
    )
    
    warehouse.store_model_run(
        model_name="St. Croix River",
        run_id=1,
        run_name="Initial Run",
        notes="Baseline model run"
    )
    
    # List all models
    print("\nModels in warehouse:")
    models = warehouse.list_models()
    print(models.to_string(index=False))
    
    # List runs for a specific model
    print("\nRuns for Nemadji River Basin:")
    runs = warehouse.list_runs(model_name="Nemadji River Basin")
    print(runs[['run_id', 'run_name', 'notes']].to_string(index=False))
    
    print("\n✓ Basic usage complete!")


def example_timeseries_storage():
    """Example of storing timeseries data."""
    print("\n=== Timeseries Storage Example ===\n")
    
    warehouse = OutputWarehouse("example_warehouse.duckdb")
    
    # First, create a model run
    run_pk = warehouse.store_model_run(
        model_name="Example Model",
        run_id=1,
        run_name="Demonstration Run"
    )
    print(f"Created model run with pk={run_pk}")
    
    # Create sample timeseries data
    # In real usage, this would come from parsing HBN files
    dates = pd.date_range(start='2020-01-01', periods=10, freq='D')
    
    # Example: streamflow data
    sample_data = pd.DataFrame({
        'datetime': dates,
        'value': [100.5, 105.2, 98.3, 103.7, 110.1, 115.8, 108.9, 102.3, 99.7, 104.2]
    })
    
    print("\nSample timeseries data:")
    print(sample_data.head())
    
    # Store the timeseries with metadata
    ts_pk = warehouse.store_timeseries(
        model_run_pk=run_pk,
        ts_name="ROVOL",
        df=sample_data,
        operation_id=101,
        operation_type="RCHRES",
        activity="HYDR",
        timestep="daily",
        unit="cfs",
        timeseries_type="instantaneous"
    )
    
    print(f"\nStored timeseries with metadata, timeseries_pk={ts_pk}")
    
    # Query the stored data
    result = warehouse.query_timeseries(model_name="Example Model", ts_name="ROVOL")
    print(f"\nQueried {len(result)} data points")
    print(result[['datetime', 'value', 'ts_name', 'unit']].head())
    
    print("\n✓ Timeseries storage example complete!")


def example_calibration_workflow():
    """Example of using warehouse during iterative calibration."""
    print("\n=== Calibration Workflow Example ===\n")
    
    warehouse = OutputWarehouse("calibration_warehouse.duckdb")
    
    # Simulate multiple calibration iterations
    model_name = "Test Basin Model"
    
    for iteration in range(1, 4):
        print(f"Calibration iteration {iteration}...")
        
        warehouse.store_model_run(
            model_name=model_name,
            run_id=iteration,
            run_name=f"Calibration Iteration {iteration}",
            notes=f"Testing parameter set {iteration}"
        )
    
    # List all calibration runs
    print("\nAll calibration runs:")
    runs = warehouse.list_runs(model_name=model_name)
    print(runs[['run_id', 'run_name']].to_string(index=False))
    
    print("\n✓ Calibration workflow example complete!")


def example_multi_model_comparison():
    """Example of storing outputs from multiple models for comparison."""
    print("\n=== Multi-Model Comparison Example ===\n")
    
    warehouse = OutputWarehouse("comparison_warehouse.duckdb")
    
    # Store runs from multiple models
    models = [
        ("Big Fork River", "2000-2010 calibration"),
        ("Little Fork River", "2000-2010 calibration"),
        ("Rainy River", "2000-2010 calibration")
    ]
    
    for model_name, description in models:
        warehouse.store_model_run(
            model_name=model_name,
            run_id=1,
            run_name="Baseline",
            notes=description
        )
    
    print("Models stored for comparison:")
    models_df = warehouse.list_models()
    print(models_df.to_string(index=False))
    
    print("\n✓ Multi-model comparison example complete!")


def example_export():
    """Example of exporting data from warehouse."""
    print("\n=== Data Export Example ===\n")
    
    warehouse = OutputWarehouse("export_warehouse.duckdb")
    
    # Store a run
    warehouse.store_model_run(
        model_name="Export Test",
        run_id=1,
        run_name="Test Run"
    )
    
    # Export to different formats
    print("Exporting data to CSV...")
    warehouse.export_run_data("Export Test", 1, "output_data.csv", format='csv')
    print("✓ Exported to output_data.csv")
    
    try:
        print("Exporting data to Parquet...")
        warehouse.export_run_data("Export Test", 1, "output_data.parquet", format='parquet')
        print("✓ Exported to output_data.parquet")
    except ImportError:
        print("⚠ Parquet export requires pyarrow (skipped)")
    
    print("Exporting data to JSON...")
    warehouse.export_run_data("Export Test", 1, "output_data.json", format='json')
    print("✓ Exported to output_data.json")
    
    print("\n✓ Export example complete!")


if __name__ == "__main__":
    print("=" * 60)
    print("OutputWarehouse Examples")
    print("=" * 60)
    print()
    
    example_basic_usage()
    example_timeseries_storage()
    example_calibration_workflow()
    example_multi_model_comparison()
    example_export()
    
    print("\n" + "=" * 60)
    print("All examples completed successfully!")
    print("=" * 60)
