# -*- coding: utf-8 -*-
"""
UCI (User Control Input) Module
================================

This module provides a Python interface for reading, manipulating, and writing
HSPF (Hydrological Simulation Program – Fortran) UCI files.  A UCI file is the
primary input configuration for an HSPF simulation and uses a fixed-width,
block-oriented text format that describes:

* **Operations** – the hydrologic elements of the model such as pervious land
  segments (``PERLND``), impervious land segments (``IMPLND``), and stream
  reaches / reservoirs (``RCHRES``).
* **Tables** – parameter sets inside each operation block (e.g.
  ``PWAT-PARM2``, ``GEN-INFO``, ``BINARY-INFO``).
* **External sources / targets** – time-series inputs (``EXT SOURCES``) and
  outputs (``EXT TARGETS``) that link the model to WDM data files.
* **Network connectivity** – the ``SCHEMATIC`` and ``MASS-LINK`` blocks that
  define how water and constituents move between operations.
* **Global settings** – simulation period, output flags, and file paths in
  the ``GLOBAL`` and ``FILES`` blocks.

Architecture
------------
The module is organized into two layers:

1. **UCI class** – the main user-facing API.  It lazily parses individual
   tables on demand (via :py:meth:`UCI.table`) and provides methods to query,
   update, and write the model configuration.
2. **Helper / setup functions** – module-level functions that operate on a
   ``UCI`` instance to perform common initialization and formatting tasks
   (e.g. ``setup_files``, ``setup_binaryinfo``).

Internally, the raw UCI text is converted into a nested dictionary of
:class:`~hspf.parser.parsers.Table` objects keyed by
``(block, table_name, table_id)`` tuples.  Each ``Table`` wraps the
fixed-width lines and can parse them into a :class:`pandas.DataFrame` using
column definitions stored in ``data/ParseTable.csv``.

Quick Start
-----------
.. code-block:: python

    from hspf.uci import UCI

    # Load a UCI file
    model = UCI("path/to/model.uci")

    # Retrieve a parsed table as a DataFrame
    pwat = model.table("PERLND", "PWAT-PARM2")

    # Modify a parameter value
    model.update_table(1.5, "PERLND", "PWAT-PARM2", 0, operator="*")

    # Write the updated UCI file
    model.write("path/to/model_updated.uci")

See Also
--------
hspf.parser.parsers : Fixed-width table parsing and the ``Table`` class.
hspf.parser.graph   : Reach-network graph utilities (``reachNetwork``).
hspf.hbn            : HBN binary output file reader.

@author: mfratki
"""


#lines = reader('C:/Users/mfratki/Documents/Projects/LacQuiParle/ucis/LacQuiParle_0.uci')
import subprocess
import sys
import numpy as np
import pandas as pd
from .parser.parsers import Table
from .parser.graph import reachNetwork

#from hspf_tools.parser import setup

from pathlib import Path


parseTable = pd.read_csv(Path(__file__).parent/'data/ParseTable.csv',
                          dtype = {'width': 'Int64',
                                  'start': 'Int64',
                                  'stop': 'Int64',
                                  'space': 'Int64'})

#timeseriesCatalog = pd.read_csv(Path(__file__).parent/'TimeseriesCatalog.csv')

#timeseriesCatalog = pd.read_csv('C:/Users/mfratki/Documents/GitHub/hspf_tools/parser/TimeseriesCatalog.csv')
#                             dtype = {'width': 'Int64',
#                                       'start': 'Int64',
#                                       'stop': 'Int64',
#                                       'space': 'Int64'})
class UCI():
    """Primary interface for reading, querying, and modifying an HSPF UCI file.

    On construction the UCI text is read, parsed into a nested dictionary of
    :class:`~hspf.parser.parsers.Table` objects, and augmented with metadata
    derived from the ``OPN SEQUENCE`` block (valid operation IDs), a
    :class:`~hspf.parser.graph.reachNetwork` graph, and—optionally—
    meteorological-zone assignments inferred from ``EXT SOURCES``.

    Parameters
    ----------
    filepath : str or pathlib.Path
        Path to the ``.uci`` file on disk.
    infer_metzones : bool, optional
        When *True* (default), meteorological zones and landcover assignments
        are inferred from the ``EXT SOURCES`` block and stored in
        :attr:`opnid_dict`.

    Attributes
    ----------
    filepath : pathlib.Path
        Absolute path to the source UCI file.
    name : str
        Model name derived from the file stem (e.g. ``"Clearwater"``).
    lines : list[str]
        Raw, non-blank lines read from the UCI file (see :func:`reader`).
    run_comments : list[str]
        Comment lines (``***``) that precede the ``RUN`` keyword.
    uci : dict[tuple, Table]
        Nested dictionary mapping ``(block, table_name, table_id)`` keys to
        :class:`~hspf.parser.parsers.Table` objects.
    valid_opnids : dict[str, list[int]]
        Operation IDs active in the simulation, keyed by operation type
        (``'PERLND'``, ``'IMPLND'``, ``'RCHRES'``, ``'GENER'``, ``'COPY'``).
    network : reachNetwork
        Directed graph of the model's reach network built from the
        ``SCHEMATIC`` and ``OPN SEQUENCE`` blocks.
    opnid_dict : dict[str, DataFrame]
        Per-operation DataFrames mapping operation IDs to meteorological zones
        and landcover indices.  Only populated when *infer_metzones* is True.
    wdm_paths : list[pathlib.Path]
        Resolved paths to WDM files referenced in the ``FILES`` block.
    hbn_paths : list[pathlib.Path]
        Resolved paths to HBN output files referenced in the ``FILES`` block.
    """

    def __init__(self, filepath, infer_metzones=True):
        self.filepath = Path(filepath)
        self.name = self.filepath.name.split('.')[0]
        self.lines = reader(filepath)
        self.run_comments = RUN_comments(self.lines)
        self.uci = build_uci(self.lines)
        self.wdm_paths = self.get_filepaths('.wdm')
        self.hbn_paths = self.get_filepaths('.hbn')

        # Require to get valid opnids - Business rule
        opnseq = self.table('OPN SEQUENCE')
        self.valid_opnids = {
            'PERLND': opnseq['SEGMENT'][opnseq['OPERATION'] == 'PERLND'].astype(int).to_list(),
            'RCHRES': opnseq['SEGMENT'][opnseq['OPERATION'] == 'RCHRES'].astype(int).to_list(),
            'IMPLND': opnseq['SEGMENT'][opnseq['OPERATION'] == 'IMPLND'].astype(int).to_list(),
            'GENER' : opnseq['SEGMENT'][opnseq['OPERATION'] == 'GENER'].astype(int).to_list(),
            'COPY'  : opnseq['SEGMENT'][opnseq['OPERATION'] == 'COPY'].astype(int).to_list(),
        }
        self.network = reachNetwork(self)

        if infer_metzones:
            self.opnid_dict = self.get_metzones()
        self._LSID_flag = 0
    
    
    # def supplemental(self):
    #     for block in ['RCHRES','PERLND','IMPLND']:
    #         keys = list([key for key in list(self.uci.keys()) if key[0] == block])
    #         for key in keys:
    #             lines = self.uci[key]
    #             for line in lines:
    #                 if '***' in line:
    #                     pass
    #                 elif '~' in line:
    #                     line.split('~') # assuming there will only ever be 2 ~ in a line
    
    def get_parameter(self, parameter):
        """Retrieve a single named parameter across all operations.

        .. note:: This method is not yet implemented.

        Parameters
        ----------
        parameter : str
            Name of the parameter to look up.

        Raises
        ------
        NotImplementedError
            Always raised; the method is reserved for future use.
        """
        raise NotImplementedError()
    
                 
    def table(self, block, table_name='na', table_id=0, drop_comments=True):
        """Parse and return a UCI table as a :class:`~pandas.DataFrame`.

        Tables are parsed lazily—the first call triggers the fixed-width
        parser.  For operation blocks (``PERLND``, ``RCHRES``, ``IMPLND``,
        ``GENER``, ``COPY``) the returned DataFrame is indexed by ``OPNID``
        after expanding any operation-ID ranges (e.g. ``"1 10"`` →
        ``[1, 2, …, 10]``) and filtering to :attr:`valid_opnids`.

        Parameters
        ----------
        block : str
            Top-level UCI block name.  Must be one of ``'GLOBAL'``,
            ``'FILES'``, ``'PERLND'``, ``'IMPLND'``, ``'RCHRES'``,
            ``'SCHEMATIC'``, ``'OPN SEQUENCE'``, ``'MASS-LINK'``,
            ``'EXT SOURCES'``, ``'NETWORK'``, ``'GENER'``, ``'MONTH-DATA'``,
            ``'EXT TARGETS'``, ``'COPY'``, or ``'FTABLES'``.
        table_name : str, optional
            Sub-table name within the block (e.g. ``'PWAT-PARM2'``,
            ``'GEN-INFO'``).  Defaults to ``'na'`` for blocks that contain a
            single anonymous table (e.g. ``'GLOBAL'``, ``'FILES'``).
        table_id : int, optional
            Ordinal index when the same table name appears more than once
            inside a block (e.g. multiple ``QUAL-PROPS`` tables).  Defaults
            to ``0``.
        drop_comments : bool, optional
            When *True* (default), rows that are comment lines are removed
            from the returned DataFrame and the ``'comments'`` column is
            dropped.

        Returns
        -------
        pandas.DataFrame
            A copy of the parsed table data.

        Raises
        ------
        AssertionError
            If *block* is not one of the recognized block names.
        KeyError
            If the ``(block, table_name, table_id)`` tuple does not exist in
            the UCI dictionary.
        """
        assert block in ['GLOBAL','FILES','PERLND','IMPLND','RCHRES','SCHEMATIC','OPN SEQUENCE','MASS-LINK','EXT SOURCES','NETWORK','GENER','MONTH-DATA','EXT TARGETS','COPY','FTABLES']
        
        table = self.uci[(block,table_name,table_id)] #[block][table_name][table_id]
        #TODO move the format_opnids into the Table class?
        if table.data is None:
            table.parse()
            if block in ['PERLND','RCHRES','IMPLND','GENER','COPY']     :
                table.replace(format_opnids(table.data,self.valid_opnids[block]))
            elif block in ['EXT SOURCES']:
                table.replace(expand_extsources(table.data,self.valid_opnids))
                
        table_data = table.data.copy()
        if drop_comments:
            table_data =table_data[table_data['comments'] == '']
            table_data = table_data.drop('comments',axis = 1)       
        
        return table_data
    
    def _table(self, block, table_name, table_id):
        """Return the raw :class:`~hspf.parser.parsers.Table` object (no copy)."""
        return self.uci[(block, table_name, table_id)]

    def replace_table(self, table, block, table_name='na', table_id=0):
        """Replace the data of an entire table in the UCI dictionary.

        Parameters
        ----------
        table : pandas.DataFrame
            New table data.  Must share the same column schema as the
            existing table.
        block : str
            Block name (e.g. ``'PERLND'``, ``'FILES'``).
        table_name : str, optional
            Sub-table name.  Defaults to ``'na'``.
        table_id : int, optional
            Ordinal index for duplicate table names.  Defaults to ``0``.
        """
        self.uci[(block, table_name, table_id)].replace(table)

    def table_lines(self, block, table_name='na', table_id=0):
        """Return a copy of the raw fixed-width text lines for a table.

        Parameters
        ----------
        block : str
            Block name.
        table_name : str, optional
            Sub-table name.  Defaults to ``'na'``.
        table_id : int, optional
            Ordinal index.  Defaults to ``0``.

        Returns
        -------
        list[str]
            A *copy* of the raw UCI lines stored in the underlying ``Table``.
        """
        return self.uci[(block, table_name, table_id)].lines.copy()

    def comments(block, table_name=None, table_id=0):
        """Return comment lines from a table.

        .. note:: This method is not yet implemented.

        Raises
        ------
        NotImplementedError
            Always raised; the method is reserved for future use.
        """
        raise NotImplementedError()

    def table_names(self, block):
        """Return the set of sub-table names present in *block*.

        Parameters
        ----------
        block : str
            Block name (e.g. ``'PERLND'``).

        Returns
        -------
        list[str]
            Unique table names found inside the block.
        """
        return list(set([key[1] for key in list(self.uci.keys()) if key[0] == block]))

    def block_names(self):
        """Return the set of top-level block names present in the UCI file.

        Returns
        -------
        set[str]
            Block names such as ``{'GLOBAL', 'FILES', 'PERLND', …}``.
        """
        return set([key[0] for key in list(self.uci.keys())])
    
    def add_comment(self, comment):
        """Add a comment line to the UCI file.

        .. note:: This method is not yet implemented.

        Raises
        ------
        NotImplementedError
            Always raised; the method is reserved for future use.
        """
        raise NotImplementedError()

    def update_table(self, value, operation, table_name, table_id, opnids=None,
                     columns=None, operator='*', axis=0):
        """Update values within a single table using an arithmetic operator.

        This is the primary method for modifying model parameters.  It first
        ensures the table has been parsed, then applies the given *operator*
        to the specified *opnids* × *columns* subset of the table data.

        Parameters
        ----------
        value : scalar or array-like
            The operand applied to the selected cells.  Interpretation depends
            on *operator*:

            * ``'*'`` – multiply existing values by *value*.
            * ``'/'`` – divide existing values by *value*.
            * ``'+'`` – add *value* to existing values.
            * ``'-'`` – subtract *value* from existing values.
            * ``'set'`` – overwrite existing values with *value*.
            * ``'chuck'`` – apply the monthly-concentration "chuck"
              adjustment (see :func:`chuck`).  Only valid for
              ``MON-IFLW-CONC`` and ``MON-GRND-CONC`` tables.
        operation : str
            Operation block name (``'PERLND'``, ``'IMPLND'``, ``'RCHRES'``,
            etc.).
        table_name : str
            Sub-table name (e.g. ``'PWAT-PARM2'``).
        table_id : int
            Ordinal index of the table within the block.
        opnids : list[int] or None, optional
            Operation IDs (row indices) to update.  When *None*, all rows are
            updated.
        columns : str, list[str], or None, optional
            Column name(s) to update.  When *None*, all columns are updated.
        operator : str, optional
            One of ``'*'``, ``'/'``, ``'+'``, ``'-'``, ``'set'``, or
            ``'chuck'``.  Defaults to ``'*'``.
        axis : int, optional
            Axis along which the operation is applied (passed through to the
            underlying ``Table`` arithmetic methods).  Defaults to ``0``.
        """
        # ensures data has been parsed and allows for determining opnids and column values
        table = self.table(operation,table_name,table_id,True)
        
        if opnids is None:
            opnids = table.index
        if columns is None:
            columns = table.columns
        
        # Cases where some tables don't have an opnid specified but the timeseries we are comparing might
        # opnids = table.index.intersection(opnids)
        
        # simple methods for changing all values by the same value/operator combination
        if operator == 'set':
            self.uci[(operation,table_name,table_id)].set_value(opnids,columns,value, axis)
        elif operator == '*':
            self.uci[(operation,table_name,table_id)].mul(opnids,columns,value, axis)
        elif operator == '/':
            self.uci[(operation,table_name,table_id)].div(opnids,columns,value, axis)
        elif operator == '-':
            self.uci[(operation,table_name,table_id)].sub(opnids,columns,value, axis)
        elif operator == '+':
            self.uci[(operation,table_name,table_id)].add(opnids,columns,value, axis)
        elif operator == 'chuck':
            assert(table_name in ['MON-IFLW-CONC','MON-GRND-CONC'])
            values = chuck(value,table).loc[opnids,columns]
            self.uci[(operation,table_name,table_id)].set_value(opnids,columns,values)
        else:
            print('Select valid operator (set,*,/,-,+')
    
    def merge_lines(self):
        """Reconstruct the full UCI text from the internal table dictionary.

        Iterates over all blocks and their tables, serializes each
        :class:`~hspf.parser.parsers.Table` back to fixed-width text, and
        reassembles the complete UCI file content (including ``RUN`` /
        ``END RUN`` delimiters).  The result is stored in :attr:`lines` and
        is ready for writing to disk via :meth:`write`.
        """
        lines = ['RUN']
        lines += self.run_comments
        
        # properly ordered blocks
        blocks = {}
        for key in self.uci.keys():
            if key[0] in blocks.keys():
                blocks[key[0]].append(key)
            else:
                blocks[key[0]] = [key]
                
        for block,keys in blocks.items():
            lines += [block]
            for key in keys:
                table = self.uci[key]
                if key[1] == 'na':
                    lines += table.lines
                else:
                    lines += [table.header]
                    lines += table.lines
                    lines += [table.footer]
                    lines += ['']
                    
            lines += ['END ' + block]
            lines += ['']
        lines += ['END RUN']
        self.lines = lines       

    def set_simulation_period(self, start_year, end_year):
        """Update the simulation start and end dates in the GLOBAL block.

        Sets the simulation window to January 1 of *start_year* through
        December 31 of *end_year* (using hour 24:00 as the end timestamp).

        Parameters
        ----------
        start_year : int
            Four-digit start year (e.g. ``2000``).
        end_year : int
            Four-digit end year (e.g. ``2020``).
        """

        # if start_hour < 10:
        #     start_hour = f'0{int(start_hour+1)}:00'
        # else:
        #     start_hour = f'{int(start_hour+1)}:00'
        
        # if end_hour < 10:
        #     end_hour = f'0{int(end_hour+1)}:00'
        # else:
        #     end_hour = f'{int(end_hour+1)}:00'

        table_lines = self.table_lines('GLOBAL')  
        for index, line in enumerate(table_lines):
            if '***' in line: #in case there are comments in the global block
                continue
            elif line.strip().startswith('START'):
                table_lines[index] = line[0:14] + f'{start_year}/01/01 00:00  ' + f'END    {end_year}/12/31 24:00'
            else:
                continue

        self.uci[('GLOBAL','na',0)].lines = table_lines

    def set_echo_flags(self, flag1, flag2):
        """Set the run-interpreter and output-level echo flags in GLOBAL.

        Parameters
        ----------
        flag1 : int
            RUN INTERP level flag.
        flag2 : int
            OUTPT level flag.
        """
        table_lines = self.table_lines('GLOBAL')  
        for index, line in enumerate(table_lines):
            if '***' in line: #in case there are comments in the global block
                continue
            elif line.strip().startswith('RUN INTERP OUTPT LEVELS'):
                table_lines[index] = f'  RUN INTERP OUTPT LEVELS    {flag1}    {flag2}'
            else:
                continue
        

        self.uci[('GLOBAL','na',0)].lines = table_lines


    def _write(self, filepath):
        """Write the current :attr:`lines` to *filepath* (internal)."""
        with open(filepath, 'w') as the_file:
            for line in self.lines:    
                the_file.write(line+'\n')

    def add_parameter_template(self, block, table_name, table_id, column,
                              parname=None, tpl_char='~', opnids=None,
                              single_template=True, group_id=''):
        """Insert a PEST / PEST++ parameter template marker into a table column.

        Replaces the numeric values in *column* with template placeholders
        that the PEST parameter-estimation framework can recognize.  When
        *single_template* is ``True`` a single placeholder is used for all
        selected rows; when ``False`` each operation ID gets its own unique
        parameter name.

        Parameters
        ----------
        block : str
            Operation block name (e.g. ``'PERLND'``).
        table_name : str
            Sub-table name (e.g. ``'PWAT-PARM2'``).
        table_id : int
            Ordinal index for the table.
        column : str
            Column whose values will be replaced with template markers.
        parname : str or None, optional
            Base parameter name.  Defaults to the lower-cased *column* name.
        tpl_char : str, optional
            Template delimiter character used by PEST (default ``'~'``).
        opnids : list[int] or None, optional
            Subset of operation IDs to template.  When *None*, all non-comment
            rows are templated.
        single_template : bool, optional
            If ``True`` (default), all rows share the same parameter name;
            if ``False``, each row receives a unique name suffixed by its
            OPNID.
        group_id : str, optional
            Optional prefix prepended to the parameter name for parameter
            grouping.

        Returns
        -------
        list[str]
            Unique PEST parameter names that were inserted into the table.
        """
        
        table = self.table(block,table_name,0,False).reset_index()
        column_names,dtypes,starts,stops = self.uci[(block,table_name,table_id)]._delimiters()
        
        width = stops[column_names.index(column)] - starts[column_names.index(column)]

        ids = ~table[column].isna() # Handle comment lines in uci
        if parname is None:
            parameter = column.lower()
        else:
            parameter = parname.lower()

        if opnids is not None:
            ids = ids & (table['OPNID'].isin(opnids))

        
        # Replace paramter name with PEST/PEST++ specification. Note this does not use the HSPF supplemental file so parameters are limited to width of uci file column
        if single_template:
            pest_param = group_id + parameter 
            template = tpl_char + pest_param + ' '*(width-len(pest_param)-2)+ tpl_char
            pest_param = [pest_param]
        else:
            pest_param = group_id + parameter +  table.loc[ids,'OPNID'].astype(str)
            pest_param = pest_param.tolist()
            template = [tpl_char + pest_param + ' '*(width-len(pest_param)-2)+ tpl_char for pest_param in pest_param]
            #template = pest_param.apply(lambda name: tpl_char + name + ' '*(width-len(name)-1)+ tpl_char)

        table.loc[ids,column] = template
        table = table.set_index('OPNID')
        self.replace_table(table,block,table_name,table_id)
        return list(set(pest_param))

    def write_tpl(self, tpl_char='~', new_tpl_path=None):
        """Write the UCI as a PEST template (``.tpl``) file.

        Calls :meth:`merge_lines` and prepends the PEST ``ptf`` header line
        before writing to disk.

        Parameters
        ----------
        tpl_char : str, optional
            Template delimiter character (default ``'~'``).
        new_tpl_path : str or pathlib.Path or None, optional
            Destination path.  Defaults to the UCI file path with a ``.tpl``
            extension.
        """
        if new_tpl_path is None:
            new_tpl_path = self.filepath.parent.joinpath(self.filepath.stem + '.tpl')
        self.merge_lines()
        self.lines.insert(0,'ptf ' + tpl_char)
        self._write(new_tpl_path)

    def write(self, new_uci_path):
        """Write the (possibly modified) UCI to a new file.

        Calls :meth:`merge_lines` to serialize the internal dictionary back
        to fixed-width text, then writes the result to *new_uci_path*.

        Parameters
        ----------
        new_uci_path : str or pathlib.Path
            Destination file path.
        """
        self.merge_lines()
        self._write(new_uci_path) 

    def _run(self, wait_for_completion=True):
        """Execute the HSPF model using the WinHSPFLt executable (internal)."""
        run_model(self.filepath, wait_for_completion=wait_for_completion)

    def update_bino(self, name):
        """Rename binary output (``.hbn``) files in the FILES table.

        Each ``BINO`` row's filename is updated so that the prefix before the
        last ``'-'`` is replaced by *name*.

        Parameters
        ----------
        name : str
            New model name prefix for the binary output files.
        """
        table = self.table('FILES',drop_comments = False) # initialize the table
        indexs = table[table['FTYPE'] == 'BINO'].index
        for index in indexs: 
            table.loc[index,'FILENAME'] = name + '-' + table.loc[index,'FILENAME'].split('-')[-1]          
        self.replace_table(table,'FILES')
        #self.uci[('FILES','na',0)].set_value(index,'FILENAME',filename)
    
    def get_metzones(self):
        """Infer meteorological-zone assignments from ``EXT SOURCES``.

        Meteorological zones are determined by which source volume numbers
        (``SVOLNO``) supply precipitation (``PREC``) to each operation.  The
        method builds a per-operation :class:`~pandas.DataFrame` mapping
        operation IDs to their source-volume zone number and, for land
        operations, the corresponding landcover identifier (``LSID``).

        Returns
        -------
        dict[str, pandas.DataFrame]
            Keys are ``'PERLND'``, ``'IMPLND'``, and ``'RCHRES'``.  Each
            DataFrame is indexed by ``TOPFST`` (the target operation ID) and
            contains at least a ``'metzone'`` column.  Land operations also
            include ``'LSID'`` and ``'landcover'`` columns; ``RCHRES``
            includes ``'RCHID'`` and ``'LKFG'``.
        """
        operations = ['PERLND','IMPLND','RCHRES']
        dic = {}
        
        extsrc = self.table('EXT SOURCES')
        # GROUP = 'EXTNL'
        # DOMAIN = 'MET'
        # tmemns = timeseriesCatalog.loc[(timeseriesCatalog['Domain'] == 'MET') & (timeseriesCatalog['Group'] == 'EXTNL'),'Member'].str.strip().to_list()
        
        # All metzones assuming every implnd,perlnd, and rchres recives precip input
        metzones = extsrc.loc[(extsrc['TMEMN'] == 'PREC') & (extsrc['TVOL'].isin(operations)),'SVOLNO'].sort_values().unique()
        metzone_map = {metzone:num for num,metzone in zip(range(len(metzones)),metzones)}
        
        
        
        for operation in operations:
            opnids = extsrc.loc[(extsrc['TMEMN'].isin(['PREC'])) & (extsrc['TVOL'] == operation),['TOPFST','SVOLNO']]
            opnids = opnids.drop_duplicates(subset = 'TOPFST')
            opnids['metzone'] = opnids['SVOLNO'].map(metzone_map).values
            opnids.set_index(['TOPFST'],inplace = True)
           
            # Only keep opnids that are recieving preciptiation inputs.
            geninfo = self.table(operation,'GEN-INFO')
            geninfo = geninfo.loc[ list(set(geninfo.index).intersection(set(opnids.index)))] .reset_index()
            geninfo = geninfo.drop_duplicates(subset = 'OPNID').sort_values(by = 'OPNID')
            if operation == 'RCHRES':
                opnids.loc[geninfo['OPNID'],['RCHID','LKFG']] = pd.NA
                opnids['RCHID'] = geninfo['RCHID'].to_list()
                opnids['LKFG'] = geninfo['LKFG'].to_list()
            else:     
                landcovers = geninfo['LSID'].unique()
                landcover_map =  {landcover:num for num,landcover in zip(range(len(landcovers)),landcovers)}
                opnids['LSID'] = pd.NA
                opnids.loc[geninfo['OPNID'],'LSID'] = geninfo['LSID'].to_list() # index of opnid is the OPNID
                opnids['landcover'] = opnids['LSID'].map(landcover_map).values
                
               
                
            dic[operation] = opnids
        return dic
    
    
    # ---- Convenience methods ------------------------------------------------

    def get_filepaths(self, file_extension):
        """Return resolved paths to FILES entries matching *file_extension*.

        Parameters
        ----------
        file_extension : str
            File extension to filter by (e.g. ``'.wdm'``, ``'.hbn'``).

        Returns
        -------
        list[pathlib.Path]
            Paths resolved relative to the directory containing the UCI file.
        """
        files = self.table('FILES')
        filepaths = files.loc[(files['FILENAME'].str.endswith(file_extension.lower())) |  (files['FILENAME'].str.endswith(file_extension.upper())),'FILENAME'].to_list()
        filepaths = [self.filepath.parent.joinpath(filepath) for filepath in filepaths]
        return filepaths
    
    def get_dsns(self, operation, opnid, smemn):
        """Look up external-source data-set numbers for an operation member.

        Joins the ``EXT SOURCES`` and ``FILES`` tables to return the WDM
        filenames and source volume numbers that feed a particular time-series
        member into a given operation.

        Parameters
        ----------
        operation : str
            Operation type (e.g. ``'PERLND'``, ``'RCHRES'``).
        opnid : int
            Target operation ID.
        smemn : str
            Source member name (e.g. ``'PREC'``, ``'APTS'``).

        Returns
        -------
        pandas.DataFrame
            Columns: ``['FILENAME', 'SVOLNO', 'SMEMN', 'TOPFST', 'TVOL']``.
        """
        dsns = self.table('EXT SOURCES')
        assert (smemn in dsns['SMEMN'].unique())
        dsns = dsns.loc[(dsns['TVOL'] == operation) & (dsns['TOPFST'] == opnid) & (dsns['SMEMN'] == smemn)]
        files = self.table('FILES').set_index('FTYPE')
        dsns.loc[:,'FILENAME'] = files.loc[dsns['SVOL'],'FILENAME'].values
        dsns = dsns[['FILENAME','SVOLNO','SMEMN','TOPFST','TVOL']]
        return dsns
    
        
    def initialize(self, name=None, default_output=4, n=5, reach_ids=None):
        """Run the full initialization sequence for a new model setup.

        Calls :func:`setup_files`, :func:`setup_binaryinfo`,
        :func:`setup_geninfo`, and :func:`setup_qualid` in order to prepare
        the UCI for simulation.

        Parameters
        ----------
        name : str or None, optional
            Model name used for binary output file naming.  Defaults to
            :attr:`name`.
        default_output : int, optional
            Default output print level for BINARY-INFO tables (default ``4``).
        n : int, optional
            Number of binary output (``BINO``) file slots to create (default
            ``5``).
        reach_ids : list[int] or None, optional
            Reach IDs that should receive a more detailed output level
            (level ``2``).
        """
        if name is None:
            name = self.name
        
        # Note that the order of these function calls matters
        setup_files(self,name,n)
        setup_binaryinfo(self,default_output = default_output,reach_ids = reach_ids)
        setup_geninfo(self)
        setup_qualid(self)

    def initialize_binary_info(self, default_output=4, reach_ids=None):
        """Re-initialize only the BINARY-INFO and GEN-INFO tables.

        A lighter alternative to :meth:`initialize` when only the output
        configuration needs refreshing.

        Parameters
        ----------
        default_output : int, optional
            Default output print level (default ``4``).
        reach_ids : list[int] or None, optional
            Reach IDs for detailed output.
        """
        setup_binaryinfo(self,default_output = default_output,reach_ids = reach_ids)
        setup_geninfo(self)

    
    def build_targets(self):
        """Build a landcover-target summary DataFrame for calibration.

        Aggregates the ``SCHEMATIC`` areas by landcover class and returns a
        DataFrame containing the UCI landcover names, numeric landcover IDs,
        total area per class, and placeholder columns for nutrient targets.

        Returns
        -------
        pandas.DataFrame
            Columns include ``'uci_name'``, ``'lc_number'``, ``'area'``,
            ``'npsl_name'``, ``'TSS'``, ``'N'``, ``'TKN'``, ``'OP'``,
            ``'BOD'``, and ``'dom_lc'`` (the dominant landcover flag).
        """
        geninfo = self.table('PERLND','GEN-INFO')  
        targets = self.opnid_dict['PERLND'].loc[:,['LSID','landcover']] #.drop_duplicates(subset = 'landcover').loc[:,['LSID','landcover']].reset_index(drop = True)
        targets.columns = ['LSID','lc_number']
        schematic = self.table('SCHEMATIC')
        schematic = schematic.astype({'TVOLNO': int, "SVOLNO": int, 'AFACTR':float})
        schematic = schematic[(schematic['SVOL'] == 'PERLND')]
        schematic = schematic[(schematic['TVOL'] == 'PERLND') | (schematic['TVOL'] == 'IMPLND') | (schematic['TVOL'] == 'RCHRES')]
        areas = []
        for lc_number in targets['lc_number'].unique():
            areas.append(np.sum([schematic['AFACTR'][schematic['SVOLNO'] == perland].sum() for perland in targets.index[targets['lc_number'] == lc_number]]))
        areas = np.array(areas)
        
        
        lc_number = targets['lc_number'].drop_duplicates()
        uci_names = geninfo.loc[targets['lc_number'].drop_duplicates().index]['LSID']
        targets = pd.DataFrame([uci_names.values,lc_number.values,areas]).transpose()
        targets.columns = ['uci_name','lc_number','area']
        targets['npsl_name'] = ''
        
        targets[['TSS','N','TKN','OP','BOD']] = ''
        
        targets['dom_lc'] = pd.NA
        targets.loc[targets['area'].astype('float').argmax(),'dom_lc'] = 1
        return targets        


# ---------------------------------------------------------------------------
# Module-level helper functions
# ---------------------------------------------------------------------------

def run_model(uci_file, wait_for_completion=True):
    """Launch the WinHSPFLt executable to run an HSPF simulation.

    Parameters
    ----------
    uci_file : pathlib.Path
        Path to the UCI input file.
    wait_for_completion : bool, optional
        When *True* (default), blocks until the simulation finishes.  When
        *False*, the process is spawned in the background and control returns
        immediately.
    """
    winHSPF = str(Path(__file__).resolve().parent.parent) + '\\bin\\WinHSPFlt\\WinHspfLt.exe'
    
    # Arguments for the subprocess
    args = [winHSPF, uci_file.as_posix()]

    if wait_for_completion:
        # Use subprocess.run to wait for the process to complete (original behavior)
        subprocess.run(args)
    else:
        # Use subprocess.Popen to run the process in the background without waiting
        # On Windows, you can use creationflags to prevent a console window from appearing
        if sys.platform.startswith('win'):
            # Use a variable for the flag to ensure it's only used on Windows
            creationflags = subprocess.CREATE_NO_WINDOW
            subprocess.Popen(args, creationflags=creationflags)
        else:
            # For other platforms (like Linux/macOS), Popen without special flags works fine
            subprocess.Popen(args)

def get_filepaths(uci, file_extension):
    """Return resolved paths to FILES entries matching *file_extension*.

    This is the module-level equivalent of :meth:`UCI.get_filepaths`.

    Parameters
    ----------
    uci : UCI
        An initialized UCI instance.
    file_extension : str
        File extension to match (e.g. ``'.wdm'``).

    Returns
    -------
    list[pathlib.Path]
    """
    files = uci.table('FILES')
    filepaths = files.loc[(files['FILENAME'].str.endswith(file_extension.lower())) |  (files['FILENAME'].str.endswith(file_extension.upper())),'FILENAME'].to_list()
    filepaths = [uci.filepath.parent.joinpath(filepath) for filepath in filepaths]
    return filepaths



def setup_files(uci, name, n=5):
    """Configure the FILES table for a new or reset model.

    Strips directory prefixes from WDM/ECH/OUT/HBN filenames, removes any
    PLT entries, and creates *n* new ``BINO`` rows with sequential binary
    output file names.

    Parameters
    ----------
    uci : UCI
        An initialized UCI instance.
    name : str
        Model name used as the binary file name prefix.
    n : int, optional
        Number of BINO file slots to create (default ``5``).
    """
    table = uci.table('FILES',drop_comments = False)
    for index, row in table.iterrows():
        filename = Path(row['FILENAME'])
        if filename.suffix in ['.wdm','.ech','.out']:
            table.loc[index,'FILENAME'] = filename.name
        if filename.suffix in ['.hbn']:
            table.loc[index,'FILENAME'] = filename.name
        if filename.suffix in ['.plt']:
            table.drop(index,inplace = True)
            
    # Get new binary number and create new BINO rows
    bino_nums = []
    invalid = table['UNIT'].values
    for num in range(15,100):
        if num not in invalid:
            bino_nums.append(num)
        if len(bino_nums) == n:
            break
        
    binary_names = [name + '-' + str(num) + '.hbn' for num in range(len( bino_nums))]
    rows = [['BINO',bino_num,binary_name,''] for bino_num,binary_name in zip(bino_nums,binary_names)]
    rows = pd.DataFrame(rows, columns = table.columns).astype({'FTYPE':'string','UNIT':'Int64','FILENAME':'string','comments':'string'} )
    # Drop old BINO rows and insert new BINO rows
    table = table.loc[table['FTYPE'] != 'BINO'].reset_index(drop=True)
    rows = pd.DataFrame(rows, columns = table.columns).astype(table.dtypes) #{'FTYPE':'string','UNIT':'Int64','FILENAME':'string','comments':'string'} )
    table = pd.concat([table,rows])
    table.reset_index(drop=True,inplace=True)
    
    # Update table in the uci
    uci.replace_table(table,'FILES')
    


def setup_geninfo(uci):
    """Distribute binary output files across operations in GEN-INFO.

    Reads the current ``BINO`` unit numbers from the ``FILES`` table and
    splits each operation's output assignments evenly across those binary
    files by updating the ``BUNIT1`` (or ``BUNITE`` for ``RCHRES``) column
    in the ``GEN-INFO`` table.

    Parameters
    ----------
    uci : UCI
        An initialized UCI instance.
    """
    # Initialize Gen-Info
    bino_nums = uci.table('FILES').set_index('FTYPE').loc['BINO','UNIT'].tolist()
    if isinstance(bino_nums,int): #Pands is poorly designed. Why would tolist not return a goddamn list...?
        bino_nums = [bino_nums]


    #opnids = uci.table(operation,'GEN-INFO').index
    # Split model output from all operations evenly across binary files
    for operation in ['RCHRES','PERLND','IMPLND']:
        binary_info = uci.table(operation, 'BINARY-INFO')
        for t_code in [2,3,4,5]:
            opnids = binary_info.index[(binary_info.iloc[:, :-2] == t_code).any(axis=1)].to_list()
            if len(opnids) > 0:
                opnids = np.array_split(opnids,len(bino_nums))
                for opnid,bino_num in zip(opnids,bino_nums):
                    if len(opnid) > 0:
                        if operation == 'RCHRES': #TODO convert BUNITE to BUNIT1 to get rid of this if statement
                            uci.update_table(bino_num,'RCHRES','GEN-INFO',0,opnids = opnid,columns = 'BUNITE',operator = 'set')
                        else:
                            uci.update_table(bino_num,operation,'GEN-INFO',0,opnids = opnid,columns = 'BUNIT1',operator = 'set')


def setup_binaryinfo(uci, default_output=4, reach_ids=None):
    """Set the default output print levels in BINARY-INFO tables.

    All activity-print columns for ``PERLND``, ``IMPLND``, and ``RCHRES``
    are set to *default_output*.  If *reach_ids* is provided, those reaches
    receive a more detailed output level (``2``) for selected activities.

    Parameters
    ----------
    uci : UCI
        An initialized UCI instance.
    default_output : int, optional
        Print-level flag applied to all operations (default ``4``).
    reach_ids : list[int] or None, optional
        Reach IDs for which selected outputs are set to level ``2``.
    """
    # Initialize Binary-Info
    uci.update_table(default_output,'PERLND','BINARY-INFO',0,
                     columns = ['AIRTPR', 'SNOWPR', 'PWATPR', 'SEDPR', 'PSTPR', 'PWGPR', 'PQALPR','MSTLPR', 'PESTPR', 'NITRPR', 'PHOSPR', 'TRACPR'],
                     operator = 'set')
    uci.update_table(default_output,'IMPLND','BINARY-INFO',0,
                     columns = ['ATMPPR', 'SNOWPR', 'IWATPR', 'SLDPR', 'IWGPR', 'IQALPR'],
                     operator = 'set')
    uci.update_table(default_output,'RCHRES','BINARY-INFO',0, 
                     columns = ['HYDRPR', 'ADCAPR', 'CONSPR', 'HEATPR', 'SEDPR', 'GQLPR', 'OXRXPR', 'NUTRPR', 'PLNKPR', 'PHCBPR'],
                     operator = 'set')
        
    uci.update_table(default_output,'PERLND','BINARY-INFO',0,columns = ['SNOWPR','SEDPR','PWATPR','PQALPR'],operator = 'set')
    uci.update_table(default_output,'IMPLND','BINARY-INFO',0,columns = ['SNOWPR','IWATPR','SLDPR','IQALPR'],operator = 'set')
    uci.update_table(default_output,'RCHRES','BINARY-INFO',0,columns = ['HYDRPR','SEDPR','HEATPR','OXRXPR','NUTRPR','PLNKPR'],operator = 'set')
    if reach_ids is not None:
        uci.update_table(2,'RCHRES','BINARY-INFO',0,columns = ['SEDPR','OXRXPR','NUTRPR','PLNKPR','HEATPR','HYDRPR'],opnids = reach_ids,operator = 'set')


def setup_qualid(uci):
    """Standardize the QUAL-ID names for PERLND and IMPLND operations.

    Sets the ``QUALID`` column in the ``QUAL-PROPS`` tables to the canonical
    names ``'NH3+NH4'``, ``'NO3'``, ``'ORTHO P'``, and ``'BOD'`` (table IDs
    0–3 for both ``PERLND`` and ``IMPLND``).

    Parameters
    ----------
    uci : UCI
        An initialized UCI instance.
    """
    #### Standardize QUAL-ID Names
    # Perlands
    uci.update_table('NH3+NH4','PERLND','QUAL-PROPS',0,columns = 'QUALID',operator = 'set')
    uci.update_table('NO3','PERLND','QUAL-PROPS',1,columns = 'QUALID',operator = 'set')
    uci.update_table('ORTHO P','PERLND','QUAL-PROPS',2,columns = 'QUALID',operator = 'set')
    uci.update_table('BOD','PERLND','QUAL-PROPS',3,columns = 'QUALID',operator = 'set')
    
    # Implands
    uci.update_table('NH3+NH4','IMPLND','QUAL-PROPS',0,columns = 'QUALID',operator = 'set')
    uci.update_table('NO3','IMPLND','QUAL-PROPS',1,columns = 'QUALID',operator = 'set')
    uci.update_table('ORTHO P','IMPLND','QUAL-PROPS',2,columns = 'QUALID',operator = 'set')
    uci.update_table('BOD','IMPLND','QUAL-PROPS',3,columns = 'QUALID',operator = 'set')




def chuck(adjustment, table):
    """Apply the "chuck" monthly-concentration adjustment algorithm.

    For each pair of adjacent months ``(M_i, M_{i+1})``:

    * If the adjustment factor is **> 1** (increasing), the *minimum* of the
      two monthly values is multiplied by the factor.
    * If the adjustment factor is **< 1** (decreasing), the *maximum* of the
      two monthly values is multiplied by the factor.
    * If the factor equals ``1``, no change is applied to that pair.

    When a cell is updated by multiple adjacent-month pairs the final value
    is the average of the individual updates.

    Parameters
    ----------
    adjustment : array-like
        Sequence of 12 multiplicative adjustment factors (one per month
        boundary).
    table : pandas.DataFrame
        Monthly concentration table indexed by OPNID with 12 month columns.

    Returns
    -------
    pandas.DataFrame
        Adjusted table with the same shape and index as *table*.
    """
    # If increasing monthly concentration increase the minimum concnetration value of Mi and Mi+1
    # If decreasing monthly concentration decrease the maximum concnetration value of Mi and Mi+1
    # If concnetration values are equal increase both equally
    table['dummy'] = table.iloc[:,0]
    zero_table = table.copy()*0
    count_table = zero_table.copy()
    for index, value in enumerate(adjustment):
            next_index = index+1             
            if value > 1:
                for row,(a,b) in enumerate(zip(table.iloc[:,index].values, table.iloc[:,next_index].values)):
                    zero_table.iloc[row,index+np.nanargmin([a,b])] += np.nanmin([a,b])*value
                    count_table.iloc[row,index+np.nanargmin([a,b])] += 1
            elif value < 1:
                for row,(a,b) in enumerate(zip(table.iloc[:,index].values, table.iloc[:,next_index].values)):
                    zero_table.iloc[row,index+np.nanargmax([a,b])] += np.nanmax([a,b])*value
                    count_table.iloc[row,index+np.nanargmax([a,b])] += 1
    
    
    zero_table.drop('dummy',axis=1,inplace=True)
    count_table.drop('dummy',axis=1,inplace=True)
    
    zero_table[count_table == 0] = table[count_table==0]
    count_table[count_table == 0] = 1
    zero_table = zero_table/count_table
    return zero_table       




def format_opnids(table, valid_opnids):
    """Expand operation-ID ranges and set the OPNID index.

    In raw UCI tables, a row can specify an ID range such as ``"1 10"`` which
    means "operations 1 through 10".  This function expands those ranges into
    individual rows, filters to *valid_opnids*, converts the ``OPNID`` column
    to ``Int64``, and sets it as the DataFrame index.

    Parameters
    ----------
    table : pandas.DataFrame
        Parsed table with an ``'OPNID'`` column (as strings).
    valid_opnids : list[int]
        Operation IDs that are active in the simulation.

    Returns
    -------
    pandas.DataFrame
        Table with ``OPNID`` as integer index and expanded rows.
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
            opnids = [opnid for opnid in opnids if opnid in valid_opnids]
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
    table = table.loc[(table['OPNID'].isin(valid_opnids)) | (table['OPNID'].isna())]
    table = table.set_index('OPNID',drop = True)
    return table

def expand_extsources(data, valid_opnids):
    """Expand target-operation ID ranges in the EXT SOURCES table.

    Similar to :func:`format_opnids` but handles the ``TOPFST``/``TOPLST``
    (first/last target operation) range columns specific to the ``EXT SOURCES``
    block.

    Parameters
    ----------
    data : pandas.DataFrame
        Parsed ``EXT SOURCES`` table.
    valid_opnids : dict[str, list[int]]
        Valid operation IDs keyed by operation type.

    Returns
    -------
    pandas.DataFrame
        Expanded table with one row per target operation ID.
    """
    start_column = 'TOPFST'
    end_column = 'TOPLST'
    indexes = data.loc[~data[end_column].isna()]#[[start_column,end_column,'']]

    for index, row in indexes.iterrows():
        opnids = np.arange(int(row[start_column]),int(row[end_column])+1)
        opnids = [opnid for opnid in opnids if opnid in valid_opnids[row['TVOL']]]

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

    opnids = sum(list(valid_opnids.values()), []) #Note slow method for collapsing lists but fine for this case
    data = data.loc[(data['TOPFST'].isin(opnids) )| (data['TOPFST'].isna())]
    
    # Only keep rows that are being simulated    
    for operation in valid_opnids.keys():
        data = data.drop(data.loc[(data['TVOL'] == operation) & ~(data['TOPFST'].isin(valid_opnids[operation]))].index)
    
    return data


def insert_rows(insertion_point, a, b, drop=True, reset_index=True):
    """Insert rows from *b* into DataFrame *a* at *insertion_point*.

    Parameters
    ----------
    insertion_point : int
        Index label in *a* at which *b*'s rows are inserted.
    a : pandas.DataFrame
        Original DataFrame.
    b : pandas.DataFrame
        Rows to insert.
    drop : bool, optional
        Drop the original row at *insertion_point* (default ``True``).
    reset_index : bool, optional
        Reset the index after insertion (default ``True``).

    Returns
    -------
    pandas.DataFrame
    """
    if drop: a = a.drop(insertion_point)
    df = pd.concat([a.loc[:insertion_point], b, a.loc[insertion_point:]])
    if reset_index: df = df.reset_index(drop=True)
    return df
    



def keep_valid_opnids(table, opnid_column, valid_opnids):
    """Filter a table to retain only rows with valid operation IDs.

    Keeps rows whose *opnid_column* value appears in the *valid_opnids* list
    for the corresponding operation type (``TVOL`` column), plus any comment
    rows.

    Parameters
    ----------
    table : pandas.DataFrame
        Table to filter.
    opnid_column : str
        Column containing the operation ID.
    valid_opnids : dict[str, list[int]]
        Valid operation IDs keyed by operation type.

    Returns
    -------
    pandas.DataFrame
        Filtered table with reset index.
    """
    table = table.reset_index(drop = True)
    valid_indexes = [table.index[(table[opnid_column].isin(valid_opnids[operation])) & (table['TVOL'] == operation)] for operation in valid_opnids.keys()]
    valid_indexes.append(table.index[table['comments'] != ''])
    table = pd.concat([table.loc[valid_index] for valid_index in valid_indexes])
    table = table.sort_index().reset_index(drop=True)
    return table


def RUN_comments(lines):
    """Extract comment lines that appear before the ``RUN`` keyword.

    Parameters
    ----------
    lines : list[str]
        Non-blank lines from the UCI file (as returned by :func:`reader`).

    Returns
    -------
    list[str]
        Comment lines (those containing ``***``) preceding ``RUN``.
    """
    # assuems no blank lines (ie lines have been read in using the reader function)
    comments = []
    
    RUN_start = lines.index('RUN')
    if RUN_start > 0:
        comment_lines = lines[:RUN_start]
    else:
        comment_lines = lines[1:]
    
    for line in comment_lines:
        if '***' in line:
            comments.append(line)
        else:
            if any(c.isalpha() for c in line):
                break
    return comments

def reader(filepath):
    """Read a UCI file and return its non-blank lines.

    Lines containing ``***`` (comments) are preserved as-is.  All other lines
    are truncated to 80 characters (the standard UCI column width) and
    trailing whitespace is stripped.  Blank lines are discarded.

    Parameters
    ----------
    filepath : str or pathlib.Path
        Path to the UCI file.

    Returns
    -------
    list[str]
        Cleaned lines ready for parsing by :func:`build_uci`.
    """
    # simple reader to return non blank, non comment and proper length lines
    
    #TODO: Address this encoding issue that seems pretty common across our text files.
    # It's not a huge deal since we are using ASCII and no information will be lost.
    with open(filepath, encoding="utf-8",errors="ignore") as fp:
        
           lines = []
           content = fp.readlines()
           for line in content:
               if line.strip():
                   if '***' in line:
                       lines.append(line.rstrip())
                   else:
                       lines.append(line[:80].rstrip())
    return lines
                                              
def decompose_perlands(metzones, landcovers):
    """Map composite perland IDs to their (metzone, landcover) components.

    In HSPF convention a perland's ID is typically the sum of a
    meteorological-zone base number and a landcover offset.  This function
    builds the reverse mapping.

    Parameters
    ----------
    metzones : iterable of int
        Meteorological zone base IDs.
    landcovers : iterable of int
        Landcover offset IDs.

    Returns
    -------
    dict[int, tuple[int, int]]
        ``{perland_id: (metzone, landcover)}``.
    """
    perlands = {}
    for metzone in metzones:
        metzone = int(metzone)
        for landcover in landcovers:
            landcover = int(landcover)
            perlands[metzone+landcover] = (metzone,landcover)
    return perlands

def split_number(s):
    """Split a string into a text head and a trailing numeric tail.

    Parameters
    ----------
    s : str
        Input string (e.g. ``"PWAT-PARM2"``).

    Returns
    -------
    tuple[str, str]
        ``(head, tail)`` where *tail* contains only the trailing digits
        and *head* is the remainder, stripped of whitespace.

    Examples
    --------
    >>> split_number("PWAT-PARM2")
    ('PWAT-PARM', '2')
    >>> split_number("GLOBAL")
    ('GLOBAL', '')
    """
    head = s.rstrip('0123456789')
    tail = s[len(head):]
    return head.strip(), tail

def get_blocks(lines):
    """Identify top-level block boundaries in the UCI line list.

    Scans *lines* in reverse order to find matching ``<BLOCK>`` /
    ``END <BLOCK>`` delimiters and records their line indices.  Only blocks
    whose names appear in ``ParseTable.csv`` are recognized.

    Parameters
    ----------
    lines : list[str]
        Non-blank lines from the UCI file.

    Returns
    -------
    dict[str, dict]
        ``{block_name: {'indcs': [start_index, end_index]}}``.
    """
    dic = {}
    shift = len(lines)-1
    for index,line in enumerate(reversed(lines)):
        if '***' in line:
            pass
        else:
            line,number = split_number(line.strip()) # Sensitive method to separate numbers
            line_strip = line.strip() + number
            if line_strip.startswith('END'):
                if (line_strip[4:] in parseTable['block'].values): # | (line_strip[4:] in structure['block'].values):
                    current_name = line_strip[4:]                
                    dic[current_name] = {}
                    dic[current_name]['indcs'] = [shift-index]
                    #names.append(current_name)
                    #start_indcs.append(shift - index)
                    #table_id.append(number)
            elif line_strip == current_name: #line_strip.startswith(current_name):
                    dic[current_name]['indcs'].append(shift-index)
                    #end_indcs.append(shift - index)
    
    # df = pd.DataFrame([names,table_id,start_indcs,end_indcs]).transpose()
    # df.columns = ['name','id','start','stop']
    return dic

def build_uci(lines):
    """Convert raw UCI text lines into a dictionary of Table objects.

    This is the main parsing entry point.  It first calls :func:`get_blocks`
    to find block boundaries, then iterates within each block to identify
    sub-tables by their header / footer lines.  Each sub-table is wrapped in
    a :class:`~hspf.parser.parsers.Table` instance whose data is *not*
    parsed yet (lazy evaluation via :meth:`Table.parse`).

    The returned dictionary uses ``(block, table_name, table_id)`` tuples as
    keys, where *table_id* is a zero-based ordinal that distinguishes
    duplicate table names within a block.

    Parameters
    ----------
    lines : list[str]
        Non-blank lines from the UCI file (as returned by :func:`reader`).

    Returns
    -------
    dict[tuple[str, str, int], Table]
        Mapping of ``(block, table_name, table_id)`` → ``Table``.
    """
    blocks = get_blocks(lines)
    current_name = None
    keys = []
    tables = []
    for k,v in blocks.items():
        if 'na' in parseTable[parseTable['block']==k]['table'].unique():
            table = Table(k,'na')
            table.lines = lines[v['indcs'][1]:v['indcs'][0]+1][1:-1]
            table.footer = lines[v['indcs'][1]:v['indcs'][0]+1][1]
            table.header = lines[v['indcs'][1]:v['indcs'][0]+1][-1]
            table.data = None
            table.indcs = v['indcs'][1]+1
            keys.append([k,'na'])
            tables.append(table)
        else:
            #block_lines = lines[v['indcs'][1]+1:v['indcs'][0]]
            for index,line in enumerate(reversed(lines[v['indcs'][1]+1:v['indcs'][0]])):   
                if '***' in line:
                    pass
                else:
                    split_line,number = split_number(line.strip()) # Sensitive method to separate numbers
                    line_strip = split_line.strip()
                    if line_strip.startswith('END'):
                        if (line_strip[4:] in parseTable['table'].values) | (line_strip[4:]+number in parseTable['table'].values):
                            current_name = (line_strip[4:] + number).strip()  
                            current_name_len = len(current_name)
                            start = v['indcs'][0]-index
                        #else: print(line)
                    elif (line_strip + number).strip()[0:current_name_len] == current_name: #line_strip.startswith(current_name):
                            end = v['indcs'][0]-index-1
                            table = Table(k,current_name)
                            table.lines = lines[end+1:start-1]
                            table.header = lines[end]
                            table.footer = lines[start-1]
                            table.data = None
                            table.indcs = end+1
                            
                            keys.append([k,current_name])
                            tables.append(table)
                            current_name = None  
                            current_name_len = None
                            
    # Cumulative count of duplicate key names as some tables appear multiple times within a block
    #   Since I am looping through the uci file backwards I have to ensure the order of the duplicate
    #   tables are properly labeled in the correct order they appear from top to bottom in the uci file.          
    keys.reverse()
    tables.reverse()
    # Can't find a base python method for cumulative counting elements. collections.Counter only sums the duplicates
    table_ids = list(pd.DataFrame(keys).groupby(by=[0,1]).cumcount())
    ordered_keys = [(key[0],key[1],table_id) for key,table_id in zip(keys,table_ids)]
    dic = dict(zip(ordered_keys,tables))
    return dic

