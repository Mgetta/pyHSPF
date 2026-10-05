import pandas as pd
import numpy as np



def update_table(uci,value,operation,table_name,table_id,opnids = None,columns = None,operator = '*',axis = 0):
    """Apply an arithmetic or assignment operation to a subset of a table.

    The target table is parsed on first access (via :meth:`table`).  The
    operation is then dispatched to the appropriate method on the
    underlying :class:`~hspf.parser.parsers.Table` object.

    Parameters
    ----------
    value : scalar or array-like
        Value(s) to use in the operation.  For ``'chuck'``, pass the
        adjustment array; for ``'set'``, the literal value to assign.
    operation : str
        Block name that contains the table (e.g. ``'PERLND'``).
    table_name : str
        Sub-table name (e.g. ``'MON-IFLW-CONC'``).
    table_id : int
        Zero-based occurrence index of the table within the block.
    opnids : array-like or None, optional
        Subset of OPNID index values to update.  When ``None`` (default),
        all rows are updated.
    columns : str, list of str, or None, optional
        Column(s) to update.  When ``None`` (default), all columns are
        updated.
    operator : str, optional
        Arithmetic operator to apply.  One of ``'set'``, ``'*'``,
        ``'/'``, ``'-'``, ``'+'``, or ``'chuck'`` (default ``'*'``).
    axis : int, optional
        Axis along which to apply the operation (passed to Table methods;
        default ``0``).

    Notes
    -----
    The ``'chuck'`` operator is only valid for ``MON-IFLW-CONC`` and
    ``MON-GRND-CONC`` table names and uses :func:`chuck` to compute
    adjusted concentration values.
    """
    table = uci.table(operation,table_name,table_id,True)
    
    if opnids is None:
        opnids = table.index
    if columns is None:
        columns = table.columns
    
    # Cases where some tables don't have an opnid specified but the timeseries we are comparing might
    # opnids = table.index.intersection(opnids)
    
    # simple methods for changing all values by the same value/operator combination
    if operator == 'set':
        uci[(operation,table_name,table_id)].set_value(opnids,columns,value, axis)
    elif operator == '*':
        uci[(operation,table_name,table_id)].mul(opnids,columns,value, axis)
    elif operator == '/':
        uci[(operation,table_name,table_id)].div(opnids,columns,value, axis)
    elif operator == '-':
        uci[(operation,table_name,table_id)].sub(opnids,columns,value, axis)
    elif operator == '+':
        uci[(operation,table_name,table_id)].add(opnids,columns,value, axis)
    elif operator == 'chuck':
        assert(table_name in ['MON-IFLW-CONC','MON-GRND-CONC'])
        values = chuck(value,table).loc[opnids,columns]
        uci[(operation,table_name,table_id)].set_value(opnids,columns,values)
    else:
        print('Select valid operator (set,*,/,-,+')



def set_simulation_period(uci,start_year,end_year):
    """Update the simulation start and end dates in the GLOBAL block.

    Locates the ``START`` line inside the GLOBAL table and rewrites it
    with ``<start_year>/01/01 00:00`` and ``<end_year>/12/31 24:00``.
    Comment lines in the GLOBAL block are skipped.

    Parameters
    ----------
    start_year : int
        Four-digit start year for the simulation.
    end_year : int
        Four-digit end year for the simulation.
    """

    # if start_hour < 10:
    #     start_hour = f'0{int(start_hour+1)}:00'
    # else:
    #     start_hour = f'{int(start_hour+1)}:00'
    
    # if end_hour < 10:
    #     end_hour = f'0{int(end_hour+1)}:00'
    # else:
    #     end_hour = f'{int(end_hour+1)}:00'

    table_lines = uci.table_lines('GLOBAL')  
    for index, line in enumerate(table_lines):
        if '***' in line: #in case there are comments in the global block
            continue
        elif line.strip().startswith('START'):
            table_lines[index] = line[0:14] + f'{start_year}/01/01 00:00  ' + f'END    {end_year}/12/31 24:00'
        else:
            continue

    uci[('GLOBAL','na',0)].lines = table_lines

def set_echo_flags(uci,flag1,flag2):
    """Update the ``RUN INTERP OUTPT LEVELS`` line in the GLOBAL block.

    Locates the line starting with ``RUN INTERP OUTPT LEVELS`` and
    replaces it with the supplied flag values.  Comment lines in the
    GLOBAL block are skipped.

    Parameters
    ----------
    flag1 : int or str
        First output level flag value.
    flag2 : int or str
        Second output level flag value.
    """
    table_lines = uci.table_lines('GLOBAL')
    for index, line in enumerate(table_lines):
        if '***' in line: #in case there are comments in the global block
            continue
        elif line.strip().startswith('RUN INTERP OUTPT LEVELS'):
            table_lines[index] = f'  RUN INTERP OUTPT LEVELS    {flag1}    {flag2}'
        else:
            continue
    

    uci.uci[('GLOBAL','na',0)].lines = table_lines



# Expanding opnid-opnid in tables
def format_opnids(table,simulated_opnids):
    """Expand range-style OPNID entries and filter to valid operation IDs.

    UCI tables sometimes encode a range of operation IDs as a single row with
    an OPNID value like ``'1 5'`` (meaning IDs 1 through 5 inclusive).  This
    function expands such rows into one row per ID, filters the result to only
    those IDs present in *simulated_opnids*, and sets OPNID as the DataFrame index.

    Parameters
    ----------
    table : pandas.DataFrame
        Parsed table data that includes an ``OPNID`` column.  Comment rows
        (where ``OPNID`` is empty) are preserved.
    simulated_opnids : list of int
        The set of active operation IDs for the block being processed
        (typically one of the per-operation lists from ``UCI.simulated_opnids``).

    Returns
    -------
    pandas.DataFrame
        Expanded and filtered table with ``OPNID`` (integer) as the index.
    """
    table = table.reset_index()
    indexes = table.loc[table[~(table['OPNID'] == '')].index,'OPNID']
    for index, value in indexes.items():
        try:
            #table.loc[index,'OPNID'] = int(value[0])
            int(value)
        except ValueError:
            value = value.split()
            opnids = np.arange(int(value[0]),int(value[1])+1)
            opnids = [opnid for opnid in opnids if opnid in simulated_opnids]
            if len(opnids) == 0: # incase the x-x mapping covers no valid opnids
                table.drop(index,inplace = True)
            else:
                df = pd.DataFrame([table.loc[index]]*len(opnids))
                df['OPNID'] = opnids
                # The insertion method takes advantage of the fact
                # that Pandas does not automatically reset indexes.
                table = insert_rows(index,table,df,reset_index = False)
    
    
    #table.loc[table.index[table['OPNID'] == ''],'OPNID'] = pd.NA
    table['OPNID'] = pd.to_numeric(table['OPNID']).astype('Int64')
    
    
    # Only keep rows that are being simulated    
    table = table.loc[(table['OPNID'].isin(simulated_opnids)) | (table['OPNID'].isna())]
    table = table.set_index('OPNID',drop = True)
    return table

def expand_extsources(data,simulated_opnids):
    """Expand range-style EXT SOURCES entries and filter to valid operation IDs.

    EXT SOURCES rows may specify a range of target operation IDs via
    ``TOPFST`` and ``TOPLST`` columns.  This function expands such rows into
    one row per operation ID, sets ``TOPLST`` to ``pd.NA`` for expanded rows,
    and then removes rows for operation IDs not present in *simulated_opnids* for
    their respective ``TVOL`` operation.

    Parameters
    ----------
    data : pandas.DataFrame
        Parsed EXT SOURCES table containing at minimum the columns
        ``TOPFST``, ``TOPLST``, and ``TVOL``.
    simulated_opnids : dict
        Mapping of operation name (e.g. ``'PERLND'``) to a list of active
        integer operation IDs (typically ``UCI.simulated_opnids``).

    Returns
    -------
    pandas.DataFrame
        Expanded and filtered EXT SOURCES table with a reset integer index.
    """
    start_column = 'TOPFST'
    end_column = 'TOPLST'
    indexes = data.loc[~data[end_column].isna()]#[[start_column,end_column,'']]

    for index, row in indexes.iterrows():
        opnids = np.arange(int(row[start_column]),int(row[end_column])+1)
        opnids = [opnid for opnid in opnids if opnid in simulated_opnids[row['TVOL']]]

        if len(opnids) == 0: # incase the x-x mapping covers no valid opnids
            data.drop(index,inplace = True)
        else:
            df = pd.DataFrame([data.loc[index]]*len(opnids))
            df[start_column] = opnids
            df[end_column] = pd.NA
            df = df.astype(data.dtypes.to_dict())
            # The insertion method takes advantage of the fact
            # that Pandas does not automatically reset indexes.
            data = insert_rows(index,data,df,reset_index = False)
    
    
    #table.loc[table.index[table['OPNID'] == ''],'OPNID'] = pd.NA
    data[start_column] = pd.to_numeric(data[start_column]).astype('Int64')
    data[end_column] = pd.to_numeric(data[end_column]).astype('Int64')
    data = data.reset_index(drop = True)

    opnids = sum(list(simulated_opnids.values()), []) #Note slow method for collapsing lists but fine for this case
    data = data.loc[(data['TOPFST'].isin(opnids) )| (data['TOPFST'].isna())]
    
    # Only keep rows that are being simulated    
    for operation in simulated_opnids.keys():
        data = data.drop(data.loc[(data['TVOL'] == operation) & ~(data['TOPFST'].isin(simulated_opnids[operation]))].index)
    
    return data


def insert_rows(insertion_point,a,b,drop = True,reset_index = True):    
    """Insert DataFrame *b* into DataFrame *a* at *insertion_point*.

    Parameters
    ----------
    insertion_point : int
        Index label in *a* at which to insert *b*.  All rows of *a* with
        label ``<= insertion_point`` precede *b*; rows with label
        ``> insertion_point`` follow it.
    a : pandas.DataFrame
        Base DataFrame.
    b : pandas.DataFrame
        Rows to insert.
    drop : bool, optional
        When ``True`` (default), the row at *insertion_point* is dropped
        from *a* before inserting *b*.
    reset_index : bool, optional
        When ``True`` (default), reset the integer index of the result.
        Set to ``False`` to preserve original index labels (used by
        :func:`format_opnids` and :func:`expand_extsources`).

    Returns
    -------
    pandas.DataFrame
        Combined DataFrame with *b* inserted at the specified position.
    """
    if drop: a = a.drop(insertion_point)
    df = pd.concat([a.loc[:insertion_point], b, a.loc[insertion_point:]])
    if reset_index: df = df.reset_index(drop=True)
    return df

