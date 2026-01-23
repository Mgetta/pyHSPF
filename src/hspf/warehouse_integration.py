"""
Integration module for persisting HSPF model outputs to the warehouse.

This module provides helper functions to extract outputs from HBN files
and store them in the OutputWarehouse database.
"""

import pandas as pd
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from .warehouse import OutputWarehouse


class ModelOutputPersister:
    """
    Helper class to persist HSPF model outputs to a warehouse.
    
    This class follows composition over inheritance and provides a
    loosely coupled interface between hspfModel and OutputWarehouse.
    
    Example:
        persister = ModelOutputPersister("models.duckdb")
        persister.persist_model_run(
            model=my_model,
            model_name="Nemadji Basin",
            run_id=1,
            run_name="Baseline"
        )
    """
    
    def __init__(self, warehouse_path: str):
        """
        Initialize the persister.
        
        Args:
            warehouse_path: Path to the warehouse database
        """
        self.warehouse = OutputWarehouse(warehouse_path)
    
    def persist_model_run(self, model, model_name: str, run_id: int,
                         run_name: Optional[str] = None,
                         notes: Optional[str] = None,
                         operations_to_save: Optional[List[str]] = None,
                         time_codes: Optional[List[int]] = None):
        """
        Persist a complete model run to the warehouse.
        
        Args:
            model: hspfModel instance with loaded HBN data
            model_name: Name of the model
            run_id: Unique identifier for this run
            run_name: Optional descriptive name
            notes: Optional notes about this run
            operations_to_save: Optional list of operations to save (e.g., ['PERLND', 'RCHRES'])
            time_codes: Optional list of time codes to save (e.g., [3, 4] for daily and monthly)
        
        Returns:
            model_run_pk: Primary key of the stored run
        """
        # Store the model run metadata
        run_pk = self.warehouse.store_model_run(
            model_name=model_name,
            run_id=run_id,
            run_name=run_name,
            notes=notes
        )
        
        # Note: Full implementation would extract timeseries from model.hbns
        # and store them in the warehouse. This is left as a minimal interface
        # to demonstrate the integration pattern.
        
        # Example of how timeseries would be extracted and stored:
        # if hasattr(model, 'hbns') and model.hbns:
        #     for hbn in model.hbns.hbns:
        #         # Extract timeseries data
        #         # Store to warehouse using warehouse.store_timeseries_data()
        #         pass
        
        return run_pk
    
    def persist_timeseries(self, df: pd.DataFrame, model_run_pk: int,
                          operation_type: str, ts_name: str,
                          activity: Optional[str] = None,
                          timestep: Optional[str] = None,
                          unit: Optional[str] = None):
        """
        Persist a single timeseries to the warehouse.
        
        Args:
            df: DataFrame with datetime index and values
            model_run_pk: Primary key of the model run
            operation_type: Type of operation (e.g., 'PERLND', 'RCHRES')
            ts_name: Name of the timeseries
            activity: Optional activity name
            timestep: Optional timestep (e.g., 'daily', 'hourly')
            unit: Optional unit (e.g., 'cfs', 'mg/l')
        """
        # This is a placeholder for the actual implementation
        # In a full implementation, this would prepare the data
        # and call warehouse.store_timeseries_data()
        pass
    
    def get_warehouse(self) -> OutputWarehouse:
        """Get the underlying warehouse instance."""
        return self.warehouse


def persist_hbn_outputs(hbn_interface, warehouse_path: str,
                       model_name: str, run_id: int,
                       run_name: Optional[str] = None) -> int:
    """
    Convenience function to persist HBN outputs directly.
    
    Args:
        hbn_interface: hbnInterface or hbnClass instance
        warehouse_path: Path to warehouse database
        model_name: Name of the model
        run_id: Run identifier
        run_name: Optional run name
        
    Returns:
        model_run_pk: Primary key of the stored run
    """
    warehouse = OutputWarehouse(warehouse_path)
    
    # Store run metadata
    run_pk = warehouse.store_model_run(
        model_name=model_name,
        run_id=run_id,
        run_name=run_name
    )
    
    # Extract and store timeseries
    # (Implementation would go here)
    
    return run_pk
