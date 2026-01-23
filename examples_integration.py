"""
Example demonstrating integration between hspfModel and OutputWarehouse.

This shows how to use the loosely coupled ModelOutputPersister to store
model outputs during calibration or scenario analysis.
"""

from hspf import OutputWarehouse, ModelOutputPersister


def example_model_calibration():
    """
    Example: Using warehouse during iterative model calibration.
    
    This demonstrates how the warehouse can be used independently
    from the model runs, following the principle of loose coupling.
    """
    print("=== Model Calibration Example ===\n")
    
    # Initialize persister with warehouse
    persister = ModelOutputPersister("calibration.duckdb")
    
    # Simulate calibration iterations
    print("Running calibration iterations...")
    
    for iteration in range(1, 5):
        # In real usage, you would:
        # 1. Modify model parameters
        # 2. Run the model
        # 3. Extract outputs from HBN files
        
        # For this example, we just store the run metadata
        run_pk = persister.persist_model_run(
            model=None,  # In real usage: your hspfModel instance
            model_name="Basin Model",
            run_id=iteration,
            run_name=f"Calibration Run {iteration}",
            notes=f"Parameter set {iteration}"
        )
        
        print(f"  Iteration {iteration}: stored as run_pk={run_pk}")
    
    # Query stored calibration runs
    warehouse = persister.get_warehouse()
    runs = warehouse.list_runs(model_name="Basin Model")
    
    print(f"\nStored {len(runs)} calibration runs:")
    print(runs[['run_id', 'run_name']].to_string(index=False))
    
    print("\n✓ Calibration example complete!")


def example_scenario_comparison():
    """
    Example: Storing outputs from different scenarios.
    
    This demonstrates composition over inheritance - the persister
    can be used with any model instance without modifying the model class.
    """
    print("\n=== Scenario Comparison Example ===\n")
    
    persister = ModelOutputPersister("scenarios.duckdb")
    
    scenarios = [
        ("Baseline", "Current land use and climate"),
        ("Future_Climate", "2050 climate projection"),
        ("BMP_Implementation", "With best management practices"),
        ("Combined", "Future climate + BMPs")
    ]
    
    print("Storing scenario runs...")
    for scenario_name, description in scenarios:
        run_pk = persister.persist_model_run(
            model=None,
            model_name="Watershed Model",
            run_id=hash(scenario_name) % 10000,  # Simple unique ID
            run_name=scenario_name,
            notes=description
        )
        print(f"  {scenario_name}: stored as run_pk={run_pk}")
    
    # List all scenarios
    warehouse = persister.get_warehouse()
    runs = warehouse.list_runs(model_name="Watershed Model")
    
    print(f"\nStored scenarios:")
    print(runs[['run_name', 'notes']].to_string(index=False))
    
    print("\n✓ Scenario comparison example complete!")


def example_multi_model_warehouse():
    """
    Example: Single warehouse for multiple independent models.
    
    This demonstrates how the warehouse can house outputs from
    completely different models, ideal for regional analysis.
    """
    print("\n=== Multi-Model Warehouse Example ===\n")
    
    # Single warehouse for all models
    warehouse_path = "regional_models.duckdb"
    
    # Different models can use the same warehouse
    models = [
        ("Big Fork River", "Northern Minnesota"),
        ("Little Fork River", "Northern Minnesota"),
        ("St. Croix River", "Eastern Minnesota/Wisconsin"),
        ("Nemadji River", "Northeastern Minnesota")
    ]
    
    print("Storing runs from multiple models...")
    for model_name, location in models:
        persister = ModelOutputPersister(warehouse_path)
        run_pk = persister.persist_model_run(
            model=None,
            model_name=model_name,
            run_id=1,
            run_name="2010-2020 Baseline",
            notes=location
        )
        print(f"  {model_name}: stored")
    
    # Query the consolidated warehouse
    warehouse = OutputWarehouse(warehouse_path)
    all_models = warehouse.list_models()
    
    print(f"\nWarehouse contains {len(all_models)} models:")
    print(all_models.to_string(index=False))
    
    print("\n✓ Multi-model warehouse example complete!")


def example_loose_coupling():
    """
    Example: Demonstrating loose coupling design.
    
    The warehouse and persister can be used completely independently
    of the model runner, enabling flexible workflows.
    """
    print("\n=== Loose Coupling Example ===\n")
    
    print("1. Model runs can be stored without a warehouse:")
    print("   (Traditional workflow - outputs stay in HBN files)")
    
    print("\n2. Warehouse can be used independently:")
    warehouse = OutputWarehouse("independent.duckdb")
    warehouse.store_model_run("Model A", 1, "Manual entry")
    print("   ✓ Run stored directly to warehouse")
    
    print("\n3. Persister provides optional integration:")
    persister = ModelOutputPersister("integrated.duckdb")
    print("   ✓ Persister created for optional use")
    
    print("\n4. Each component has a single responsibility:")
    print("   - hspfModel: Run simulations")
    print("   - OutputWarehouse: Store and query outputs")
    print("   - ModelOutputPersister: Bridge between them")
    
    print("\n✓ Loose coupling example complete!")


if __name__ == "__main__":
    print("=" * 60)
    print("OutputWarehouse Integration Examples")
    print("=" * 60)
    print()
    
    example_model_calibration()
    example_scenario_comparison()
    example_multi_model_warehouse()
    example_loose_coupling()
    
    print("\n" + "=" * 60)
    print("All integration examples completed!")
    print("=" * 60)
    print("\nNote: In production, you would pass actual hspfModel")
    print("instances to persist_model_run() to extract and store")
    print("timeseries data from HBN files.")
