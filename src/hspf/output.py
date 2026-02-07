# -*- coding: utf-8 -*-
"""
Output writing module for HSPF model results.

Provides organized output from the model with support for:
- reach_ids: one or more modeled reaches that define outlet outputs of interest
- constituent: a constituent of interest (Q, TSS, TP, etc.)
- time_step: time step of simulated output (typically daily for reaches)

The module separates getting output from writing output so data can be passed
directly to pyhcal without having to write to disk first.

@author: pyHSPF contributors
"""
import logging
import pandas as pd
from pathlib import Path
from typing import List, Optional, Union

logger = logging.getLogger(__name__)


class OutputWriter:
    """
    Provides organized output from HSPF model results.
    
    Separates getting output (returns data) from writing output (writes to disk)
    so output can be passed directly to pyhcal without writing to disk.
    
    Parameters
    ----------
    hbns : hbnInterface
        Interface to HBN binary output files. Required for all output methods.
    uci : UCI, optional
        UCI model configuration object. Currently not used directly by OutputWriter,
        but may be needed for future report extensions. Pass when available.
    wdms : wdmInterface, optional
        Interface to WDM input/output files. Currently not used directly by OutputWriter,
        but may be needed for future report extensions. Pass when available.
    
    Notes
    -----
    All get_* and write_* methods require only `hbns` to be provided.
    The `uci` and `wdms` parameters are reserved for future report extensions.
    
    Examples
    --------
    >>> from hspf import hspfModel
    >>> model = hspfModel('path/to/model.uci')
    >>> writer = OutputWriter(model.hbns, model.uci)
    >>> 
    >>> # Get flow data for analysis with pyhcal
    >>> flow_data = writer.get_reach_output(reach_ids=[90], constituent='Q', time_step='daily')
    >>> 
    >>> # Write flow data to CSV file
    >>> writer.write_reach_output('output.csv', reach_ids=[90], constituent='Q', time_step='daily')
    """
    
    TIME_STEP_MAP = {
        'hourly': 'h',
        'daily': 'D',
        'monthly': 'ME',
        'yearly': 'YE',
        'h': 'h',
        'D': 'D',
        'ME': 'ME',
        'YE': 'YE',
        2: 'h',
        3: 'D',
        4: 'ME',
        5: 'YE'
    }
    
    def __init__(self, hbns, uci=None, wdms=None):
        """
        Initialize the OutputWriter.
        
        Parameters
        ----------
        hbns : hbnInterface
            Interface to HBN binary output files
        uci : UCI, optional
            UCI model configuration object
        wdms : wdmInterface, optional
            Interface to WDM input/output files
        """
        self.hbns = hbns
        self.uci = uci
        self.wdms = wdms
    
    def _normalize_time_step(self, time_step: Union[str, int]) -> str:
        """Convert time_step to pandas-compatible frequency string."""
        if time_step in self.TIME_STEP_MAP:
            return self.TIME_STEP_MAP[time_step]
        return time_step
    
    def _normalize_reach_ids(self, reach_ids: Union[int, List[int]]) -> List[int]:
        """Ensure reach_ids is a list."""
        if isinstance(reach_ids, int):
            return [reach_ids]
        return list(reach_ids)
    
    # =========================================================================
    # GET methods - return data for analysis with pyhcal
    # =========================================================================
    
    def get_reach_output(
        self,
        reach_ids: Union[int, List[int]],
        constituent: str,
        time_step: Union[str, int] = 'daily',
        unit: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get simulated output for specified reaches.
        
        This method returns data that can be passed directly to pyhcal
        for comparison with observed data.
        
        Parameters
        ----------
        reach_ids : int or list of int
            One or more modeled reaches that define outlet outputs of interest.
            Use negative reach_id to subtract flow (e.g., for water balance).
        constituent : str
            Constituent of interest. Options: 'Q', 'TSS', 'TP', 'OP', 'N', 'TKN', 'WT'
        time_step : str or int, default 'daily'
            Time step of simulated output. Options: 'hourly', 'daily', 'monthly', 'yearly'
            or numeric codes (2=hourly, 3=daily, 4=monthly, 5=yearly)
        unit : str, optional
            Unit for output. If None, defaults are used based on constituent:
            - Q: 'cfs'
            - TSS, TP, OP, N, TKN: 'mg/l'
            - WT: 'degF'
        
        Returns
        -------
        pd.DataFrame
            DataFrame with DatetimeIndex and one column per reach_id.
            Attributes include 'unit', 'constituent', and 'reach_ids'.
        
        Examples
        --------
        >>> # Get daily flow at outlet
        >>> flow = writer.get_reach_output(reach_ids=[90], constituent='Q')
        >>> 
        >>> # Get monthly TSS at multiple reaches
        >>> tss = writer.get_reach_output(
        ...     reach_ids=[10, 50, 90],
        ...     constituent='TSS',
        ...     time_step='monthly'
        ... )
        """
        reach_ids = self._normalize_reach_ids(reach_ids)
        time_step_code = self._normalize_time_step(time_step)
        
        return self.hbns.get_reach_constituent(
            constituent=constituent,
            reach_ids=reach_ids,
            time_step=time_step_code,
            unit=unit
        )
    
    def get_perlnd_output(
        self,
        constituent: str,
        time_step: Union[str, int] = 'yearly',
        perlnd_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Get simulated output for pervious land segments.
        
        Parameters
        ----------
        constituent : str
            Constituent of interest. Options: 'TSS', 'Q', 'TP', 'OP', 'N', 'TKN'
        time_step : str or int, default 'yearly'
            Time step of simulated output.
        perlnd_ids : list of int, optional
            Specific PERLND IDs to include. If None, includes all.
        
        Returns
        -------
        pd.DataFrame
            DataFrame with DatetimeIndex and one column per PERLND.
        """
        time_step_code = self._normalize_time_step(time_step)
        return self.hbns.get_perlnd_constituent(
            constituent=constituent,
            perlnd_ids=perlnd_ids,
            time_step=time_step_code
        )
    
    def get_implnd_output(
        self,
        constituent: str,
        time_step: Union[str, int] = 'yearly',
        implnd_ids: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Get simulated output for impervious land segments.
        
        Parameters
        ----------
        constituent : str
            Constituent of interest. Options: 'TSS', 'Q', 'TP', 'OP', 'N', 'TKN'
        time_step : str or int, default 'yearly'
            Time step of simulated output.
        implnd_ids : list of int, optional
            Specific IMPLND IDs to include. If None, includes all.
        
        Returns
        -------
        pd.DataFrame
            DataFrame with DatetimeIndex and one column per IMPLND.
        """
        time_step_code = self._normalize_time_step(time_step)
        return self.hbns.get_implnd_constituent(
            constituent=constituent,
            implnd_ids=implnd_ids,
            time_step=time_step_code
        )
    
    # =========================================================================
    # WRITE methods - write data to disk
    # =========================================================================
    
    def write_reach_output(
        self,
        filepath: Union[str, Path],
        reach_ids: Union[int, List[int]],
        constituent: str,
        time_step: Union[str, int] = 'daily',
        unit: Optional[str] = None,
        format: str = 'csv'
    ) -> Path:
        """
        Write simulated reach output to a file.
        
        Parameters
        ----------
        filepath : str or Path
            Output file path.
        reach_ids : int or list of int
            One or more modeled reaches.
        constituent : str
            Constituent of interest.
        time_step : str or int, default 'daily'
            Time step of simulated output.
        unit : str, optional
            Unit for output.
        format : str, default 'csv'
            Output format. Options: 'csv', 'excel', 'hdf5'
        
        Returns
        -------
        Path
            Path to the written file.
        
        Examples
        --------
        >>> writer.write_reach_output(
        ...     'flow_data.csv',
        ...     reach_ids=[90],
        ...     constituent='Q',
        ...     time_step='daily'
        ... )
        """
        df = self.get_reach_output(
            reach_ids=reach_ids,
            constituent=constituent,
            time_step=time_step,
            unit=unit
        )
        
        return self._write_dataframe(df, filepath, format)
    
    def write_perlnd_output(
        self,
        filepath: Union[str, Path],
        constituent: str,
        time_step: Union[str, int] = 'yearly',
        perlnd_ids: Optional[List[int]] = None,
        format: str = 'csv'
    ) -> Path:
        """
        Write simulated PERLND output to a file.
        
        Parameters
        ----------
        filepath : str or Path
            Output file path.
        constituent : str
            Constituent of interest.
        time_step : str or int, default 'yearly'
            Time step of simulated output.
        perlnd_ids : list of int, optional
            Specific PERLND IDs to include.
        format : str, default 'csv'
            Output format. Options: 'csv', 'excel', 'hdf5'
        
        Returns
        -------
        Path
            Path to the written file.
        """
        df = self.get_perlnd_output(
            constituent=constituent,
            time_step=time_step,
            perlnd_ids=perlnd_ids
        )
        
        return self._write_dataframe(df, filepath, format)
    
    def write_implnd_output(
        self,
        filepath: Union[str, Path],
        constituent: str,
        time_step: Union[str, int] = 'yearly',
        implnd_ids: Optional[List[int]] = None,
        format: str = 'csv'
    ) -> Path:
        """
        Write simulated IMPLND output to a file.
        
        Parameters
        ----------
        filepath : str or Path
            Output file path.
        constituent : str
            Constituent of interest.
        time_step : str or int, default 'yearly'
            Time step of simulated output.
        implnd_ids : list of int, optional
            Specific IMPLND IDs to include.
        format : str, default 'csv'
            Output format. Options: 'csv', 'excel', 'hdf5'
        
        Returns
        -------
        Path
            Path to the written file.
        """
        df = self.get_implnd_output(
            constituent=constituent,
            time_step=time_step,
            implnd_ids=implnd_ids
        )
        
        return self._write_dataframe(df, filepath, format)
    
    # =========================================================================
    # REPORT methods - get ad-hoc reports and summaries
    # =========================================================================
    
    def get_summary(
        self,
        reach_ids: Union[int, List[int]],
        constituents: Optional[List[str]] = None,
        time_step: Union[str, int] = 'yearly'
    ) -> pd.DataFrame:
        """
        Get a summary report for specified reaches and constituents.
        
        Parameters
        ----------
        reach_ids : int or list of int
            One or more modeled reaches.
        constituents : list of str, optional
            List of constituents to include. If None, defaults to
            ['Q', 'TSS', 'TP', 'TKN', 'N', 'OP']
        time_step : str or int, default 'yearly'
            Time step for aggregation.
        
        Returns
        -------
        pd.DataFrame
            Summary statistics for each constituent and reach.
        """
        reach_ids = self._normalize_reach_ids(reach_ids)
        
        if constituents is None:
            constituents = ['Q', 'TSS', 'TP', 'TKN', 'N', 'OP']
        
        summaries = []
        skipped_constituents = []
        for constituent in constituents:
            try:
                df = self.get_reach_output(
                    reach_ids=reach_ids,
                    constituent=constituent,
                    time_step=time_step
                )
                
                summary = df.describe()
                summary['constituent'] = constituent
                summaries.append(summary)
            except (KeyError, TypeError, AttributeError) as e:
                # Log warning for unavailable constituents
                logger.warning(
                    f"Constituent '{constituent}' not available for reach_ids={reach_ids}: {e}"
                )
                skipped_constituents.append(constituent)
                continue
        
        if skipped_constituents:
            logger.info(
                f"Skipped {len(skipped_constituents)} unavailable constituent(s): "
                f"{skipped_constituents}"
            )
        
        if summaries:
            result = pd.concat(summaries)
            result = result.reset_index().rename(columns={'index': 'statistic'})
            return result
        
        return pd.DataFrame()
    
    def get_annual_summary(
        self,
        reach_ids: Union[int, List[int]],
        constituent: str,
        unit: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get annual summary statistics for a constituent.
        
        Parameters
        ----------
        reach_ids : int or list of int
            One or more modeled reaches.
        constituent : str
            Constituent of interest.
        unit : str, optional
            Unit for output.
        
        Returns
        -------
        pd.DataFrame
            Annual values with summary statistics.
        """
        df = self.get_reach_output(
            reach_ids=reach_ids,
            constituent=constituent,
            time_step='yearly',
            unit=unit
        )
        
        return df
    
    def get_monthly_summary(
        self,
        reach_ids: Union[int, List[int]],
        constituent: str,
        unit: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get monthly average values for a constituent.
        
        Parameters
        ----------
        reach_ids : int or list of int
            One or more modeled reaches.
        constituent : str
            Constituent of interest.
        unit : str, optional
            Unit for output.
        
        Returns
        -------
        pd.DataFrame
            Monthly average values grouped by month.
        """
        df = self.get_reach_output(
            reach_ids=reach_ids,
            constituent=constituent,
            time_step='monthly',
            unit=unit
        )
        
        # Group by month and calculate mean
        return df.groupby(df.index.month).mean()
    
    def write_summary(
        self,
        filepath: Union[str, Path],
        reach_ids: Union[int, List[int]],
        constituents: Optional[List[str]] = None,
        time_step: Union[str, int] = 'yearly',
        format: str = 'csv'
    ) -> Path:
        """
        Write summary report to a file.
        
        Parameters
        ----------
        filepath : str or Path
            Output file path.
        reach_ids : int or list of int
            One or more modeled reaches.
        constituents : list of str, optional
            List of constituents to include.
        time_step : str or int, default 'yearly'
            Time step for aggregation.
        format : str, default 'csv'
            Output format.
        
        Returns
        -------
        Path
            Path to the written file.
        """
        df = self.get_summary(
            reach_ids=reach_ids,
            constituents=constituents,
            time_step=time_step
        )
        
        return self._write_dataframe(df, filepath, format)
    
    # =========================================================================
    # Helper methods
    # =========================================================================
    
    def _write_dataframe(
        self,
        df: pd.DataFrame,
        filepath: Union[str, Path],
        format: str = 'csv'
    ) -> Path:
        """Write a DataFrame to a file in the specified format."""
        filepath = Path(filepath)
        
        if format == 'csv':
            df.to_csv(filepath)
        elif format == 'excel':
            df.to_excel(filepath)
        elif format == 'hdf5':
            df.to_hdf(filepath, key='data', mode='w')
        else:
            raise ValueError(f"Unsupported format: {format}. Use 'csv', 'excel', or 'hdf5'")
        
        return filepath
    
    def available_constituents(self) -> dict:
        """
        Get available output constituents from the HBN files.
        
        Returns
        -------
        dict
            Dictionary mapping activity names to available constituent names.
        """
        return self.hbns.output_names()
