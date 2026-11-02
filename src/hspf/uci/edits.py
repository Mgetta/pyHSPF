import pandas as pd
import numpy as np

from hspf.uci.parsing import resolve_policy




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
    
    data = uci.table(operation,table_name,table_id,False)

            
        

    #TODO: Improve how the different tables are handled. I have been getting lucky so far mixing opnids as an index in some tables and not in others that don't have them.

    
    if opnids is None:
        opnids = data.index
    if columns is None:
        columns = data.columns

        #Super hack. Will normalize eventually.
    policy = resolve_policy(operation)
    if policy.key_column is not None:
        data = data.reset_index(drop=False)
        opnids = list(data.index[data[policy.key_column].isin(opnids)])

    #table index values where 
    # Cases where some tables don't have an opnid specified but the timeseries we are comparing might
    # opnids = table.index.intersection(opnids)
    
    # simple methods for changing all values by the same value/operator combination
    if operator == 'set':
        uci.uci[(operation,table_name,table_id)].set_value(opnids,columns,value, axis)
    elif operator == '*':
        uci.uci[(operation,table_name,table_id)].mul(opnids,columns,value, axis)
    elif operator == '/':
        uci.uci[(operation,table_name,table_id)].div(opnids,columns,value, axis)
    elif operator == '-':
        uci.uci[(operation,table_name,table_id)].sub(opnids,columns,value, axis)
    elif operator == '+':
        uci.uci[(operation,table_name,table_id)].add(opnids,columns,value, axis)
    # elif operator == 'chuck':
    #     assert(table_name in ['MON-IFLW-CONC','MON-GRND-CONC'])
    #     values = chuck(value,table).loc[opnids,columns]
    #     uci.uci[(operation,table_name,table_id)].set_value(opnids,columns,values)
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




