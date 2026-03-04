# -*- coding: utf-8 -*-
"""
Utility functions for weighted statistics and time aggregation.
"""
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Period constants
# ---------------------------------------------------------------------------

#: Mapping from human-readable simulation period names to HBN time-step codes.
SIMULATION_PERIOD_TO_TIME_STEP = {
    'hourly': 2,
    'daily': 3,
    'monthly': 4,
    'seasonal': 4,   # same as monthly, but with different grouping
    'yearly': 5,
}

#: Ordered list of period granularities from finest to coarsest.
#: 'simulation' is a special sentinel meaning "the entire simulation span".
PERIOD_ORDER = ['hourly', 'daily', 'monthly', 'seasonal', 'yearly', 'simulation']


def simulation_period_to_time_step(simulation_period):
    """Convert a *simulation_period* string to the integer HBN time-step code.

    Parameters
    ----------
    simulation_period : str
        One of 'hourly', 'daily', 'monthly', 'yearly'.

    Returns
    -------
    int
        HBN time-step code (2–5).

    Raises
    ------
    ValueError
        If *simulation_period* is not recognised.
    """
    if simulation_period not in SIMULATION_PERIOD_TO_TIME_STEP:
        raise ValueError(
            f"simulation_period must be one of "
            f"{list(SIMULATION_PERIOD_TO_TIME_STEP.keys())}, "
            f"got '{simulation_period}'"
        )
    return SIMULATION_PERIOD_TO_TIME_STEP[simulation_period]


def validate_periods(simulation_period, aggregation_period):
    """Validate that *aggregation_period* ≥ *simulation_period*.

    Both values must come from :data:`PERIOD_ORDER`.  When they are equal no
    temporal aggregation should be performed.

    Parameters
    ----------
    simulation_period : str
        Resolution of the raw model output.
    aggregation_period : str or None
        Period over which to aggregate.  ``None`` means "same as
        *simulation_period*" (i.e. no aggregation).

    Raises
    ------
    ValueError
        If either period is unrecognised or if *aggregation_period* is finer
        than *simulation_period*.
    """
    if simulation_period not in PERIOD_ORDER:
        raise ValueError(
            f"simulation_period must be one of {PERIOD_ORDER}, "
            f"got '{simulation_period}'"
        )
    if aggregation_period is not None and aggregation_period not in PERIOD_ORDER:
        raise ValueError(
            f"aggregation_period must be one of {PERIOD_ORDER} or None, "
            f"got '{aggregation_period}'"
        )
    if aggregation_period is not None:
        sim_idx = PERIOD_ORDER.index(simulation_period)
        agg_idx = PERIOD_ORDER.index(aggregation_period)
        if agg_idx < sim_idx:
            raise ValueError(
                f"aggregation_period ('{aggregation_period}') cannot be finer "
                f"than simulation_period ('{simulation_period}')"
            )


def aggregation_period_to_temporal_grouping(simulation_period, aggregation_period):
    """Derive the *temporal_grouping* value from the period pair.

    Returns
    -------
    str or None
        The internal temporal-grouping key, or ``None`` when no temporal
        grouping column is needed (raw output or full-simulation aggregate).
    """
    if aggregation_period is None:
        return None
    mapping = {
        'monthly': 'month',
        'seasonal': 'season',
        'yearly': 'year',
        'simulation': None,   # overall aggregate – no grouping column
    }
    return mapping.get(aggregation_period)


def weighted_describe(df, value_col, weight_col):
    """
    Calculate weighted statistics for a DataFrame.
    
    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe
    value_col : str
        Column name for values to analyze
    weight_col : str
        Column name for weights
        
    Returns
    -------
    pd.DataFrame
        DataFrame with weighted statistics
    """
    total_weight = df[weight_col].sum()
    weighted_mean = (df[value_col] * df[weight_col]).sum() / total_weight
    weighted_var = ((df[value_col] - weighted_mean) ** 2 * df[weight_col]).sum() / total_weight
    weighted_std = np.sqrt(weighted_var)
    
    return pd.DataFrame({
        'area': [total_weight],
        f'weighted_mean_{value_col}': [weighted_mean],
        f'weighted_std_{value_col}': [weighted_std]
    })



def weighted_parameter(uci,operation, table_name, table_id, parameter, opnids = None):
    

    values = uci.table(operation,table_name,table_id)[['parameter']]
    if opnids is not None:
        values = values.loc[opnids].reset_index()

    values['OPERATION'] = operation

        # Merge with network data
    df = pd.merge(
        uci.network.subwatersheds().reset_index(),
        df,
        left_on=['SVOLNO', 'SVOL'],
        right_on=['OPNID', 'OPERATION'],
        how='inner'
    )

    df = (
    df.groupby(['TVOLNO'])[[parameter, "AFACTR"]]
    .apply(lambda x: weighted_describe(x, parameter, "AFACTR"))
    .droplevel(2)
    .reset_index()
    )
    
    return df

def weighted_output(
    uci, 
    hbn, 
    ts_name, 
    operation='PERLND', 
    t_code=5, 
    opnids=None, 
    weight_by='catchment',
    time_agg=None,
    time_agg_funcs=None
):
    """
    Calculate weighted outputs from timeseries data.
    
    Parameters
    ----------
    uci : object
        UCI object containing network and operation data
    hbn : object
        HBN object with timeseries data
    ts_name : str
        Timeseries name to analyze
    operation : str, default 'PERLND'
        Operation type
    t_code : int, default 5
        Time code
    opnids : list, optional
        Operation IDs to filter
    weight_by : str, default 'catchment'
        Grouping method: 'catchment', 'lsid', 'metzone', or 'landcover'
    time_agg : str, optional
        Time aggregation frequency (e.g., 'D', 'M', 'Y')
    time_agg_funcs : dict, optional
        Custom aggregation functions for columns after time grouping
        Example: {'weighted_mean_value': 'mean', 'area': 'sum'}
        
    Returns
    -------
    pd.DataFrame
        Weighted statistics grouped by specified dimension
    """
    # Define grouping column mapping
    WEIGHT_BY_MAPPING = {
        'catchment': 'TVOLNO',
        'lsid': 'LSID',
        'metzone': 'metzone'
    }
    
    if weight_by not in WEIGHT_BY_MAPPING:
        raise ValueError(
            f"weight_by must be one of {list(WEIGHT_BY_MAPPING.keys())}, got '{weight_by}'"
        )
    
    # Get and prepare timeseries data
    df = (
        hbn.get_multiple_timeseries(operation, t_code, ts_name, opnids=opnids)
        .reset_index()
        .melt(var_name='OPNID', value_name='value', id_vars=['datetime'])
    )
    
    # Add metadata
    df['OPERATION'] = operation
    df['ts_name'] = ts_name
    
    # Merge with network data
    df = pd.merge(
        uci.network.subwatersheds().reset_index(),
        df,
        left_on=['SVOLNO', 'SVOL'],
        right_on=['OPNID', 'OPERATION'],
        how='inner'
    )
    
    # Merge with metzone data
    df = pd.merge(
        df,
        uci.opnid_dict[operation]['metzone'],
        left_on='OPNID',
        right_on='TOPFST',
        how='inner'
    )
    
    # Select relevant columns
    df = df[['TVOLNO', 'OPERATION', 'OPNID', 'AFACTR', 'LSID', 'metzone', 'ts_name', 'datetime', 'value']]
    
    # Group by spatial dimension and calculate weighted statistics
    group_col = WEIGHT_BY_MAPPING[weight_by]
    df = (
        df.groupby(['datetime', group_col])[['value', 'AFACTR']]
        .apply(lambda x: weighted_describe(x, 'value', 'AFACTR'))
        .droplevel(2)
        .reset_index()
    )
    
    df['ts_name'] = ts_name
    
    # Apply time aggregation if requested
    if time_agg is not None:
        df = _apply_time_aggregation(df, time_agg, group_col, time_agg_funcs)
    
    return df


def _apply_time_aggregation(df, freq, group_col, agg_funcs=None):
    """
    Apply time-based aggregation to weighted statistics.
    
    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe with datetime index
    freq : str
        Pandas frequency string (e.g., 'D', 'M', 'Y')
    group_col : str
        Spatial grouping column to preserve
    agg_funcs : dict, optional
        Custom aggregation functions per column
        
    Returns
    -------
    pd.DataFrame
        Time-aggregated dataframe
    """
    # Set default aggregation functions if not provided
    if agg_funcs is None:
        # Default: means are averaged, areas are summed
        agg_funcs = {
            col: 'mean' if 'mean' in col or 'std' in col else 'sum'
            for col in df.columns
            if col not in ['datetime', group_col, 'ts_name']
        }
    
    # Ensure datetime is datetime type
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    # Create time period column
    df['time_period'] = df['datetime'].dt.to_period(freq)
    
    # Group and aggregate
    result = (
        df.groupby(['time_period', group_col])
        .agg(agg_funcs)
        .reset_index()
    )
    
    # Convert period back to timestamp
    result['datetime'] = result['time_period'].dt.to_timestamp()
    result = result.drop(columns=['time_period'])
    
    # Restore ts_name
    result['ts_name'] = df['ts_name'].iloc[0]
    
    return result


def weighted_mean(df,value_col,weight_col):
    total = df[weight_col].sum()
    if total == 0:
        df = pd.DataFrame({
            'AFACTR' : 0,
            value_col: [np.nan]})
    else:
        weighted_mean = (df[value_col] * df[weight_col]).sum() / df[weight_col].sum()
        df = pd.DataFrame({
            'AFACTR' : df[weight_col].sum(),
            value_col: [weighted_mean]})
    return df
                            
def annual_weighted_output(uci,hbn,ts_name,operation = 'PERLND',t_code = 5,opnids = None,group_by = None,start_year = 1996,end_year = 2100):
    assert (group_by in [None,'landcover','opnid'])
    df = hbn.get_multiple_timeseries(operation,t_code,ts_name,opnids = opnids)
    df = df.loc[(df.index.year >= start_year) & (df.index.year <= end_year)]   
    df = df.mean().reset_index() 
    df.columns = ['SVOLNO',ts_name]
    subwatersheds = uci.network.subwatersheds().reset_index()
    subwatersheds = subwatersheds.loc[subwatersheds['SVOL'] == operation]
            
          
    df = pd.merge(subwatersheds,df,left_on = 'SVOLNO', right_on='SVOLNO',how='left')
    
    
    if group_by is None:
        df = weighted_mean(df,ts_name,'AFACTR')
    elif group_by == 'landcover':
        df = df.groupby('LSID')[[ts_name,'AFACTR']].apply(lambda x: weighted_mean(x,ts_name,'AFACTR')).droplevel(1)
    elif group_by == 'opnid':
        df = df.groupby(df['SVOLNO'])[[ts_name,'AFACTR']].apply(lambda x: weighted_mean(x,ts_name,'AFACTR')).droplevel(1)
    
    df = df.set_index([df.index,'AFACTR'])
    return df


def add_temporal_groups(df,time_step):
    assert 'datetime' in df.columns, "DataFrame must have a 'datetime' column"
    if time_step <= 5:
        df['year'] = df['datetime'].dt.year
    if time_step <= 4:
        df['month'] = df['datetime'].dt.month
        df['season'] = df['datetime'].dt.month.map(
    {12:'winter',1:'winter',2:'winter',3:'spring',4:'spring',5:'spring',
     6:'summer',7:'summer',8:'summer',9:'fall',10:'fall',11:'fall'})
    if time_step <= 3:
        df['day'] = df['datetime'].dt.day
    if time_step <= 2:
        df['hour'] = df['datetime'].dt.hour

    return df