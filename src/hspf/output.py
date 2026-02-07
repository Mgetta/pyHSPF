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


class ReportWriter:
    """
    Provides organized report generation from HSPF model results.
    
    Separates getting reports (returns data) from writing reports (writes to disk)
    so report data can be passed directly to pyhcal or other analysis tools
    without writing to disk.
    
    This class wraps the existing Reports class functionality with a consistent
    get_*/write_* API pattern.
    
    Parameters
    ----------
    reports : Reports
        The Reports object from an hspfModel instance.
    
    Notes
    -----
    ReportWriter delegates to the existing Reports class for all calculations.
    It provides a consistent API with:
    - get_* methods: Return DataFrame for analysis/passing to pyhcal
    - write_* methods: Write report to disk in various formats
    
    Examples
    --------
    >>> from hspf import hspfModel
    >>> model = hspfModel('path/to/model.uci')
    >>> rw = ReportWriter(model.reports)
    >>> 
    >>> # Get scour report for analysis
    >>> scour_data = rw.get_scour_report()
    >>> 
    >>> # Write water budget to CSV
    >>> rw.write_water_budget('water_budget.csv', operation='PERLND')
    """
    
    def __init__(self, reports):
        """
        Initialize the ReportWriter.
        
        Parameters
        ----------
        reports : Reports
            The Reports object from an hspfModel instance.
        """
        self.reports = reports
    
    # =========================================================================
    # GET methods - return report data for analysis
    # =========================================================================
    
    def get_scour_report(
        self,
        start_year: str = '1996',
        end_year: str = '2030'
    ) -> 'pd.DataFrame':
        """
        Get channel scour report.
        
        Calculates the ratio of nonpoint source loading to total loading
        including channel scour/deposition for each reach.
        
        Parameters
        ----------
        start_year : str, default '1996'
            Start year for averaging.
        end_year : str, default '2030'
            End year for averaging.
        
        Returns
        -------
        pd.DataFrame
            Scour report with columns: RCHID, LKFG, nonpoint, depscour, ratio
        """
        return self.reports.scour(start_year=start_year, end_year=end_year)
    
    def get_landcover_area(self) -> 'pd.DataFrame':
        """
        Get landcover area summary.
        
        Returns
        -------
        pd.DataFrame
            Area and percent by landcover type.
        """
        return self.reports.landcover_area()
    
    def get_water_budget(self, operation: str = 'PERLND') -> 'pd.DataFrame':
        """
        Get annual water budget report.
        
        Parameters
        ----------
        operation : str, default 'PERLND'
            Operation type. Options: 'PERLND', 'IMPLND', 'RCHRES'
        
        Returns
        -------
        pd.DataFrame
            Annual water budget components.
        """
        return self.reports.annual_water_budget(operation)
    
    def get_sediment_budget(self) -> 'pd.DataFrame':
        """
        Get annual sediment budget report.
        
        Returns
        -------
        pd.DataFrame
            Annual sediment budget.
        """
        return self.reports.annual_sediment_budget()
    
    def get_subwatershed_loading(self, constituent: str) -> 'pd.DataFrame':
        """
        Get annual average subwatershed loading.
        
        Parameters
        ----------
        constituent : str
            Constituent of interest. Options: 'Q', 'TSS', 'TP', 'TKN', 'N', 'OP'
        
        Returns
        -------
        pd.DataFrame
            Loading by subwatershed with weighted mean and area.
        """
        return self.reports.ann_avg_subwatershed_loading(constituent)
    
    def get_watershed_loading(
        self,
        constituent: str,
        reach_ids: Union[int, List[int]]
    ) -> 'pd.DataFrame':
        """
        Get annual average watershed loading by landcover.
        
        Parameters
        ----------
        constituent : str
            Constituent of interest. Options: 'Q', 'TSS', 'TP', 'TKN', 'N', 'OP'
        reach_ids : int or list of int
            Outlet reach IDs for the watershed.
        
        Returns
        -------
        pd.DataFrame
            Loading by landcover with volume, area, and share metrics.
        """
        if isinstance(reach_ids, int):
            reach_ids = [reach_ids]
        return self.reports.ann_avg_watershed_loading(constituent, reach_ids)
    
    def get_yield(
        self,
        constituent: str,
        reach_ids: Union[int, List[int]]
    ) -> 'pd.DataFrame':
        """
        Get annual average yield.
        
        Parameters
        ----------
        constituent : str
            Constituent of interest. Options: 'Q', 'TSS', 'TP', 'TKN', 'N', 'OP'
        reach_ids : int or list of int
            Outlet reach IDs for yield calculation.
        
        Returns
        -------
        pd.DataFrame
            Average annual yield.
        """
        if isinstance(reach_ids, int):
            reach_ids = [reach_ids]
        return self.reports.ann_avg_yield(constituent, reach_ids)
    
    def get_annual_precip(self) -> 'pd.DataFrame':
        """
        Get average annual precipitation report.
        
        Returns
        -------
        pd.DataFrame
            Average annual precipitation by operation and DSN.
        """
        return self.reports.annual_precip()
    
    def get_simulated_et(self) -> 'pd.DataFrame':
        """
        Get simulated evapotranspiration report.
        
        Returns
        -------
        pd.DataFrame
            Simulated ET data.
        """
        return self.reports.simulated_et()
    
    # =========================================================================
    # WRITE methods - write reports to disk
    # =========================================================================
    
    def write_scour_report(
        self,
        filepath: Union[str, Path],
        start_year: str = '1996',
        end_year: str = '2030',
        format: str = 'csv'
    ) -> Path:
        """
        Write channel scour report to file.
        
        Parameters
        ----------
        filepath : str or Path
            Output file path.
        start_year : str, default '1996'
            Start year for averaging.
        end_year : str, default '2030'
            End year for averaging.
        format : str, default 'csv'
            Output format. Options: 'csv', 'excel', 'hdf5'
        
        Returns
        -------
        Path
            Path to the written file.
        """
        df = self.get_scour_report(start_year=start_year, end_year=end_year)
        return self._write_dataframe(df, filepath, format)
    
    def write_landcover_area(
        self,
        filepath: Union[str, Path],
        format: str = 'csv'
    ) -> Path:
        """
        Write landcover area report to file.
        
        Parameters
        ----------
        filepath : str or Path
            Output file path.
        format : str, default 'csv'
            Output format. Options: 'csv', 'excel', 'hdf5'
        
        Returns
        -------
        Path
            Path to the written file.
        """
        df = self.get_landcover_area()
        return self._write_dataframe(df, filepath, format)
    
    def write_water_budget(
        self,
        filepath: Union[str, Path],
        operation: str = 'PERLND',
        format: str = 'csv'
    ) -> Path:
        """
        Write annual water budget report to file.
        
        Parameters
        ----------
        filepath : str or Path
            Output file path.
        operation : str, default 'PERLND'
            Operation type. Options: 'PERLND', 'IMPLND', 'RCHRES'
        format : str, default 'csv'
            Output format. Options: 'csv', 'excel', 'hdf5'
        
        Returns
        -------
        Path
            Path to the written file.
        """
        df = self.get_water_budget(operation=operation)
        return self._write_dataframe(df, filepath, format)
    
    def write_sediment_budget(
        self,
        filepath: Union[str, Path],
        format: str = 'csv'
    ) -> Path:
        """
        Write annual sediment budget report to file.
        
        Parameters
        ----------
        filepath : str or Path
            Output file path.
        format : str, default 'csv'
            Output format. Options: 'csv', 'excel', 'hdf5'
        
        Returns
        -------
        Path
            Path to the written file.
        """
        df = self.get_sediment_budget()
        return self._write_dataframe(df, filepath, format)
    
    def write_subwatershed_loading(
        self,
        filepath: Union[str, Path],
        constituent: str,
        format: str = 'csv'
    ) -> Path:
        """
        Write subwatershed loading report to file.
        
        Parameters
        ----------
        filepath : str or Path
            Output file path.
        constituent : str
            Constituent of interest.
        format : str, default 'csv'
            Output format. Options: 'csv', 'excel', 'hdf5'
        
        Returns
        -------
        Path
            Path to the written file.
        """
        df = self.get_subwatershed_loading(constituent=constituent)
        return self._write_dataframe(df, filepath, format)
    
    def write_watershed_loading(
        self,
        filepath: Union[str, Path],
        constituent: str,
        reach_ids: Union[int, List[int]],
        format: str = 'csv'
    ) -> Path:
        """
        Write watershed loading report to file.
        
        Parameters
        ----------
        filepath : str or Path
            Output file path.
        constituent : str
            Constituent of interest.
        reach_ids : int or list of int
            Outlet reach IDs for the watershed.
        format : str, default 'csv'
            Output format. Options: 'csv', 'excel', 'hdf5'
        
        Returns
        -------
        Path
            Path to the written file.
        """
        df = self.get_watershed_loading(constituent=constituent, reach_ids=reach_ids)
        return self._write_dataframe(df, filepath, format)
    
    def write_yield(
        self,
        filepath: Union[str, Path],
        constituent: str,
        reach_ids: Union[int, List[int]],
        format: str = 'csv'
    ) -> Path:
        """
        Write yield report to file.
        
        Parameters
        ----------
        filepath : str or Path
            Output file path.
        constituent : str
            Constituent of interest.
        reach_ids : int or list of int
            Outlet reach IDs.
        format : str, default 'csv'
            Output format. Options: 'csv', 'excel', 'hdf5'
        
        Returns
        -------
        Path
            Path to the written file.
        """
        df = self.get_yield(constituent=constituent, reach_ids=reach_ids)
        return self._write_dataframe(df, filepath, format)
    
    def write_annual_precip(
        self,
        filepath: Union[str, Path],
        format: str = 'csv'
    ) -> Path:
        """
        Write annual precipitation report to file.
        
        Parameters
        ----------
        filepath : str or Path
            Output file path.
        format : str, default 'csv'
            Output format. Options: 'csv', 'excel', 'hdf5'
        
        Returns
        -------
        Path
            Path to the written file.
        """
        df = self.get_annual_precip()
        return self._write_dataframe(df, filepath, format)
    
    def write_simulated_et(
        self,
        filepath: Union[str, Path],
        format: str = 'csv'
    ) -> Path:
        """
        Write simulated ET report to file.
        
        Parameters
        ----------
        filepath : str or Path
            Output file path.
        format : str, default 'csv'
            Output format. Options: 'csv', 'excel', 'hdf5'
        
        Returns
        -------
        Path
            Path to the written file.
        """
        df = self.get_simulated_et()
        return self._write_dataframe(df, filepath, format)
    
    # =========================================================================
    # Helper methods
    # =========================================================================
    
    def _write_dataframe(
        self,
        df: 'pd.DataFrame',
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
    
    def available_reports(self) -> List[str]:
        """
        Get list of available report types.
        
        Returns
        -------
        list of str
            Names of available reports.
        """
        return [
            'scour_report',
            'landcover_area',
            'water_budget',
            'sediment_budget',
            'subwatershed_loading',
            'watershed_loading',
            'yield',
            'annual_precip',
            'simulated_et'
        ]
