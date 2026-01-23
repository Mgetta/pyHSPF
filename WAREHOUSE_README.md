# HSPF Output Warehouse

This module provides a database/warehouse solution for storing and managing HSPF model outputs from multiple models, scenarios, and runs.

## Features

- **Loosely Coupled Design**: The `OutputWarehouse` class uses composition over inheritance and can be used independently
- **Multi-Model Support**: Store outputs from different models in a single warehouse
- **Multi-Run Storage**: Track multiple runs for each model/scenario (ideal for calibration)
- **Flexible Querying**: Query and filter stored outputs by model, run, operation type, and timeseries name
- **Multiple Export Formats**: Export data to CSV, JSON, or Parquet formats
- **DuckDB Backend**: Fast, embedded analytical database requiring no separate server

## Quick Start

```python
from hspf import OutputWarehouse

# Create or connect to a warehouse
warehouse = OutputWarehouse("my_models.duckdb")

# Store a model run
warehouse.store_model_run(
    model_name="Nemadji River Basin",
    run_id=1,
    run_name="Baseline Calibration",
    notes="Initial calibration run for 2010-2020"
)

# List all models in the warehouse
models = warehouse.list_models()
print(models)

# List runs for a specific model
runs = warehouse.list_runs(model_name="Nemadji River Basin")
print(runs)
```

## Use Cases

### Iterative Model Calibration

During calibration, you often need to run the model multiple times with different parameter sets. The warehouse makes it easy to track all calibration runs:

```python
warehouse = OutputWarehouse("calibration.duckdb")

for iteration in range(1, 10):
    # Run model with new parameters
    # ...
    
    # Store the run
    warehouse.store_model_run(
        model_name="My Basin Model",
        run_id=iteration,
        run_name=f"Calibration Run {iteration}",
        notes=f"LZSN={lzsn_value}, UZSN={uzsn_value}"
    )
```

### Multi-Model Comparison

Store outputs from different models for comparison and visualization:

```python
warehouse = OutputWarehouse("regional_models.duckdb")

models = ["Big Fork", "Little Fork", "Rainy River"]
for model_name in models:
    warehouse.store_model_run(
        model_name=model_name,
        run_id=1,
        run_name="2010-2020 Baseline"
    )

# Later, query all models for comparison
all_models = warehouse.list_models()
```

### Scenario Analysis

Compare different management or climate scenarios for the same model:

```python
scenarios = [
    ("Baseline", "Current conditions"),
    ("BMP_Implementation", "With best management practices"),
    ("Future_Climate", "2050 climate projection")
]

for scenario_name, description in scenarios:
    warehouse.store_model_run(
        model_name="Watershed Model",
        run_id=hash(scenario_name),
        run_name=scenario_name,
        notes=description
    )
```

## Architecture

The warehouse follows these design principles:

1. **Composition over Inheritance**: `OutputWarehouse` composes functionality rather than extending base classes
2. **Loose Coupling**: The warehouse can be used independently of the HSPF model runner
3. **Single Responsibility**: Each method has a clear, focused purpose
4. **Data Persistence**: Uses DuckDB for efficient analytical queries without a separate database server

## Database Schema

The warehouse maintains the following core tables:

- `model_runs`: Registry of all model runs with metadata
- `hspf.timeseries_metadata`: Metadata for each timeseries (operation, activity, units, etc.)
- `hspf.timeseries`: Actual timeseries data points
- Additional tables for model structure, parameters, and hierarchy

## Examples

See `examples_warehouse.py` for complete working examples including:

- Basic warehouse usage
- Timeseries storage
- Calibration workflows
- Multi-model comparisons
- Data export

## Running Tests

```bash
python tests/test_warehouse.py
```

## Dependencies

- DuckDB: Embedded analytical database
- Pandas: Data manipulation and analysis
