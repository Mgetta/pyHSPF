# -*- coding: utf-8 -*-
"""
UCI file handling for HSPF (Hydrological Simulation Program - Fortran) models.

This module provides tools to read, parse, manipulate, and write UCI (User
Control Input) files used by HSPF.  The central class :class:`UCI` loads a
UCI text file into a collection of :class:`~hspf.parser.parsers.Table` objects
and exposes methods for querying and modifying individual tables, updating
simulation periods, managing binary output configuration, building PEST/PEST++
parameter templates, and running the model executable.

Module-level helper functions cover file I/O (``reader``, ``get_blocks``,
``build_uci``), table post-processing (``format_opnids``,
``expand_extsources``, ``insert_rows``, ``keep_valid_opnids``), model
execution (``run_model``), and UCI initialisation workflows (``setup_files``,
``setup_geninfo``, ``setup_binaryinfo``, ``setup_qualid``).
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
class UCI():
    """Represent an HSPF UCI (User Control Input) file.

    Parses a UCI text file into a dictionary of
    :class:`~hspf.parser.parsers.Table` objects, keyed by
    ``(block, table_name, table_id)`` tuples.  Provides methods to read,
    modify, and write those tables as well as higher-level workflows for
    binary-output initialisation and PEST template generation.

    Attributes
    ----------
    filepath : pathlib.Path
        Resolved path of the UCI file on disk.
    name : str
        Stem of the UCI filename (no directory, no extension).
    lines : list of str
        Raw text lines of the UCI file as read by :func:`reader`.
    run_comments : list of str
        Comment lines that appear before the ``RUN`` keyword.
    uci : dict
        Mapping of ``(block, table_name, table_id)`` tuples to
        :class:`~hspf.parser.parsers.Table` objects.
    wdm_paths : list of pathlib.Path
        Paths to WDM files referenced in the FILES block.
    hbn_paths : list of pathlib.Path
        Paths to HBN binary-output files referenced in the FILES block.
    valid_opnids : dict
        Mapping of operation name (``'PERLND'``, ``'RCHRES'``, etc.) to a
        list of active integer segment IDs taken from the OPN SEQUENCE table.
    network : reachNetwork
        Reach-network graph built from the UCI schematic.
    opnid_dict : dict or None
        Per-operation DataFrames with met-zone and land-cover assignments,
        populated when *infer_metzones* is ``True``.
    """

    def __init__(self, filepath,infer_metzones = True):
        """Initialise a UCI object by reading and parsing the given file.

        Reads the file with :func:`reader`, extracts run-level comments, builds
        the internal ``uci`` dict via :func:`build_uci`, derives
        ``valid_opnids`` from the OPN SEQUENCE table, constructs the reach
        network, and optionally infers meteorological zone assignments.

        Parameters
        ----------
        filepath : str or pathlib.Path
            Path to the UCI file to load.
        infer_metzones : bool, optional
            When ``True`` (default), call :meth:`get_metzones` during
            initialisation and store the result in ``self.opnid_dict``.
        """
        self.filepath = Path(filepath)
        self.name = self.filepath.name.split('.')[0]
        self.lines = reader(filepath)
        self.run_comments = RUN_comments(self.lines)
        self.uci = build_uci(self.lines) # UCI converted into a nested dictionary. # Could convert into a class with only tables? 
        self.wdm_paths = self.get_filepaths('.wdm')
        self.hbn_paths = self.get_filepaths('.hbn')

        # Require to get valid opnids - Business rule
        opnseq = self.table('OPN SEQUENCE')
        self.valid_opnids=  {'PERLND': opnseq['SEGMENT'][opnseq['OPERATION'] == 'PERLND'].astype(int).to_list(),
                             'RCHRES': opnseq['SEGMENT'][opnseq['OPERATION'] == 'RCHRES'].astype(int).to_list(),
                             'IMPLND': opnseq['SEGMENT'][opnseq['OPERATION'] == 'IMPLND'].astype(int).to_list(),
                             'GENER' : opnseq['SEGMENT'][opnseq['OPERATION'] == 'GENER'].astype(int).to_list(),
                             'COPY'  : opnseq['SEGMENT'][opnseq['OPERATION'] == 'COPY'].astype(int).to_list()}
        self.network = reachNetwork(self)

        if infer_metzones:
            self.opnid_dict = self.get_metzones()
        self._LSID_flag = 0

        #compositions or totally separate classes?
        # self.network = network class
        # tableParser - Responsible for converting uci text to and from a pandas dataframe
        # tableUpdater - Responsible for updating individual tables
    
    
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
    
    def get_parameter(self,parameter):
        """Return the value of a named parameter.

        Parameters
        ----------
        parameter : str
            Name of the parameter to retrieve.

        Raises
        ------
        NotImplementedError
            Always; this method is not yet implemented.
        """
        raise NotImplementedError()
    
                 
    def table(self,block,table_name = 'na',table_id = 0,drop_comments = True):
        """Return the parsed data for a UCI table as a DataFrame.

        Tables are parsed lazily: on the first access the raw text lines are
        converted to a :class:`pandas.DataFrame` and cached on the
        :class:`~hspf.parser.parsers.Table` object.  Operation blocks
        (PERLND, RCHRES, IMPLND, GENER, COPY) have their OPNID columns
        expanded and filtered through :func:`format_opnids`; EXT SOURCES rows
        are expanded through :func:`expand_extsources`.

        Parameters
        ----------
        block : str
            Block name (e.g. ``'PERLND'``, ``'GLOBAL'``, ``'EXT SOURCES'``).
            Must be one of the recognised UCI block names.
        table_name : str, optional
            Sub-table name within the block (default ``'na'`` for blocks with a
            single implicit table).
        table_id : int, optional
            Zero-based index used when the same table name appears multiple
            times within a block (default ``0``).
        drop_comments : bool, optional
            When ``True`` (default), remove rows that contain only a comment
            and drop the ``comments`` column from the returned DataFrame.

        Returns
        -------
        pandas.DataFrame
            A copy of the parsed table data.
        """
        assert block in ['GLOBAL','FILES','PERLND','IMPLND','RCHRES','SCHEMATIC','OPN SEQUENCE','MASS-LINK','EXT SOURCES','NETWORK','GENER','MONTH-DATA','EXT TARGETS','COPY','FTABLES','PLTGEN']
        
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
    
    def _table(self,block,table_name,table_id):
        """Return the raw :class:`~hspf.parser.parsers.Table` object.

        Parameters
        ----------
        block : str
            Block name.
        table_name : str
            Sub-table name within the block.
        table_id : int
            Zero-based occurrence index of the table within the block.

        Returns
        -------
        hspf.parser.parsers.Table
            The internal Table object (not a copy).
        """
        return self.uci[(block,table_name,table_id)]
    
    def replace_table(self,table,block,table_name = 'na',table_id = 0): #replace an entire table 
        """Replace the data stored in a UCI table.

        Delegates to :meth:`~hspf.parser.parsers.Table.replace` on the
        underlying :class:`~hspf.parser.parsers.Table` object so that
        subsequent calls to :meth:`merge_lines` will serialise the new data.

        Parameters
        ----------
        table : pandas.DataFrame
            New data to store.  Column names and dtypes must be compatible with
            the original table schema.
        block : str
            Block name.
        table_name : str, optional
            Sub-table name (default ``'na'``).
        table_id : int, optional
            Zero-based occurrence index (default ``0``).
        """
        self.uci[(block,table_name,table_id)].replace(table)

    def table_lines(self,block,table_name = 'na',table_id = 0):
        """Return a copy of the raw text lines for a table.

        Parameters
        ----------
        block : str
            Block name.
        table_name : str, optional
            Sub-table name (default ``'na'``).
        table_id : int, optional
            Zero-based occurrence index (default ``0``).

        Returns
        -------
        list of str
            A shallow copy of the list of raw text lines stored on the
            underlying :class:`~hspf.parser.parsers.Table` object.
        """
        return self.uci[(block,table_name,table_id)].lines.copy()
        
    def comments(block,table_name = None,table_id = 0): # comments of a table
        """Return comment lines for a table.

        Parameters
        ----------
        block : str
            Block name.
        table_name : str or None, optional
            Sub-table name (default ``None``).
        table_id : int, optional
            Zero-based occurrence index (default ``0``).

        Raises
        ------
        NotImplementedError
            Always; this method is not yet implemented.
        """
        raise NotImplementedError()
        
    def table_names(self,block):
        """Return the unique sub-table names present within a block.

        Parameters
        ----------
        block : str
            Block name (e.g. ``'PERLND'``).

        Returns
        -------
        list of str
            Deduplicated list of table names found under the given block.
        """
        return list(set([key[1] for key in list(self.uci.keys()) if key[0] == block]))
        
    def block_names(self): #blocks present in a particular uci file
        """Return the set of block names present in this UCI file.

        Returns
        -------
        set of str
            Block names (e.g. ``{'GLOBAL', 'FILES', 'PERLND', ...}``).
        """
        return set([key[0] for key in list(self.uci.keys())])
    
    def add_comment(self,comment):
        """Add a comment to the UCI file.

        Parameters
        ----------
        comment : str
            Comment text to insert.

        Raises
        ------
        NotImplementedError
            Always; this method is not yet implemented.
        """
        raise NotImplementedError()
                
    def update_table(self,value,operation,table_name,table_id,opnids = None,columns = None,operator = '*',axis = 0):
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
    
    def merge_lines(self): # write uci to a txt file
        """Reconstitute the UCI text from internal Table objects.

        Assembles the full list of text lines in proper UCI block order:
        ``RUN``, run-level comment lines, each block with its tables
        (including ``END <table>`` / ``END <block>`` markers), and a
        closing ``END RUN``.  The result is stored in ``self.lines``,
        overwriting the previously read content.

        Notes
        -----
        This method must be called before :meth:`_write`, :meth:`write`, or
        :meth:`write_tpl` to ensure any in-memory edits are serialised.
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

    def set_simulation_period(self,start_year,end_year):
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

        table_lines = self.table_lines('GLOBAL')  
        for index, line in enumerate(table_lines):
            if '***' in line: #in case there are comments in the global block
                continue
            elif line.strip().startswith('START'):
                table_lines[index] = line[0:14] + f'{start_year}/01/01 00:00  ' + f'END    {end_year}/12/31 24:00'
            else:
                continue

        self.uci[('GLOBAL','na',0)].lines = table_lines

    def set_echo_flags(self,flag1,flag2):
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
        for index, line in enumerate(table_lines):
            if '***' in line: #in case there are comments in the global block
                continue
            elif line.strip().startswith('RUN INTERP OUTPT LEVELS'):
                table_lines[index] = f'  RUN INTERP OUTPT LEVELS    {flag1}    {flag2}'
            else:
                continue
        

        self.uci[('GLOBAL','na',0)].lines = table_lines


    def _write(self,filepath):
        """Write ``self.lines`` to a text file.

        Each element of ``self.lines`` is written as a separate line
        terminated by ``'\\n'``.  Call :meth:`merge_lines` first to ensure
        the lines reflect any in-memory edits.

        Parameters
        ----------
        filepath : str or pathlib.Path
            Destination file path.  The file is created or overwritten.
        """
        with open(filepath, 'w') as the_file:
            for line in self.lines:    
                the_file.write(line+'\n')

    def add_parameter_template(self,block,table_name,table_id,column,parname = None,tpl_char = '~',opnids = None,single_template = True, group_id = ''):
        """Insert PEST/PEST++ parameter template markers into a table column.

        Replaces cell values in *column* with template strings of the form
        ``~parname~`` (padded to the column width) so that a PEST ``.tpl``
        file can be generated via :meth:`write_tpl`.

        Parameters
        ----------
        block : str
            Block name containing the target table.
        table_name : str
            Sub-table name.
        table_id : int
            Zero-based occurrence index of the table.
        column : str
            Name of the column whose values will be replaced by template
            markers.
        parname : str or None, optional
            Base parameter name.  Defaults to the lower-cased *column* name.
        tpl_char : str, optional
            Template delimiter character used in the ``.tpl`` file
            (default ``'~'``).
        opnids : list of int or None, optional
            Restrict template insertion to these OPNID values.  When ``None``
            (default), all non-comment rows are updated.
        single_template : bool, optional
            When ``True`` (default), use a single shared parameter name for
            all selected rows.  When ``False``, append each row's OPNID to
            the parameter name to create per-opnid parameters.
        group_id : str, optional
            Prefix string prepended to the parameter name, used to group
            related parameters (default ``''``).

        Returns
        -------
        list of str
            Unique parameter name(s) written into the template markers.
        """
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

    def write_tpl(self,tpl_char = '~',new_tpl_path = None):    
        """Write a PEST parameter template (``.tpl``) file.

        Calls :meth:`merge_lines` to serialise current in-memory state, then
        inserts ``'ptf <tpl_char>'`` as the first line before writing.  The
        resulting file is compatible with PEST and PEST++ template-file
        conventions.

        Parameters
        ----------
        tpl_char : str, optional
            Template delimiter character (default ``'~'``).
        new_tpl_path : str or pathlib.Path or None, optional
            Destination path for the ``.tpl`` file.  Defaults to the same
            directory and stem as the UCI file with a ``.tpl`` extension.
        """
        if new_tpl_path is None:
            new_tpl_path = self.filepath.parent.joinpath(self.filepath.stem + '.tpl')
        self.merge_lines()
        self.lines.insert(0,'ptf ' + tpl_char)
        self._write(new_tpl_path)

    def write(self,new_uci_path):
        """Write the UCI to disk at the specified path.

        Calls :meth:`merge_lines` to serialise the current in-memory state
        and then :meth:`_write` to persist it.

        Parameters
        ----------
        new_uci_path : str or pathlib.Path
            Destination path for the UCI file.  The file is created or
            overwritten.
        """
        self._write(new_uci_path) 

    def _run(self,wait_for_completion=True):
        """Run the HSPF model using this UCI file.

        Delegates to the module-level :func:`run_model` function.

        Parameters
        ----------
        wait_for_completion : bool, optional
            When ``True`` (default), block until the model process exits.
            When ``False``, launch the process in the background.
        """

    def update_bino(self,name):
        """Update binary-output (BINO) filenames in the FILES table.

        For every row in the FILES table whose ``FTYPE`` is ``'BINO'``,
        replaces the filename prefix (everything before the last ``'-'``)
        with *name*, preserving the original suffix (e.g. numeric index and
        ``.hbn`` extension).

        Parameters
        ----------
        name : str
            New prefix to use for all BINO filenames.
        """
        table = self.table('FILES',drop_comments = False) # initialize the table
        indexs = table[table['FTYPE'] == 'BINO'].index
        for index in indexs: 
            table.loc[index,'FILENAME'] = name + '-' + table.loc[index,'FILENAME'].split('-')[-1]          
        self.replace_table(table,'FILES')
        #self.uci[('FILES','na',0)].set_value(index,'FILENAME',filename)
    
    def get_metzones(self):
        """Infer meteorological zone assignments from the EXT SOURCES table.

        For each operation (PERLND, IMPLND, RCHRES), identifies which
        operation IDs receive PREC (precipitation) input, maps them to met
        zones based on the ``SVOLNO`` column of EXT SOURCES, and merges with
        GEN-INFO to attach land-cover (LSID) or reach (RCHID/LKFG) metadata.

        Returns
        -------
        dict
            Mapping of operation name (``'PERLND'``, ``'IMPLND'``,
            ``'RCHRES'``) to a :class:`pandas.DataFrame` containing at
            minimum the columns ``metzone`` and ``SVOLNO``.  PERLND and
            IMPLND DataFrames additionally contain ``LSID`` and ``landcover``
            columns; RCHRES DataFrames contain ``RCHID`` and ``LKFG``.
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
    
    
# Convience methods. TODO: put in separate module that takes uci object as input. Should not be instance method
    def get_filepaths(self,file_extension):
        """Return file paths from the FILES table matching the given extension.

        Parameters
        ----------
        file_extension : str
            File extension to filter by, including the leading dot
            (e.g. ``'.wdm'``).  The comparison is case-insensitive.

        Returns
        -------
        list of pathlib.Path
            Absolute paths constructed by joining each matching filename with
            the directory that contains the UCI file.
        """
        filepaths = files.loc[(files['FILENAME'].str.endswith(file_extension.lower())) |  (files['FILENAME'].str.endswith(file_extension.upper())),'FILENAME'].to_list()
        filepaths = [self.filepath.parent.joinpath(filepath) for filepath in filepaths]
        return filepaths
    
    def get_dsns(self,operation,opnid,smemn):
        """Return dataset numbers (DSNs) for a given operation, OPNID, and member name.

        Looks up matching rows in the EXT SOURCES table, then joins with the
        FILES table to attach the source filename to each DSN record.

        Parameters
        ----------
        operation : str
            Target volume operation name (``TVOL``), e.g. ``'RCHRES'``.
        opnid : int
            Target operation ID (``TOPFST``) to filter on.
        smemn : str
            Source member name (e.g. ``'PREC'``, ``'EVAP'``).  Must be
            present in the ``SMEMN`` column of EXT SOURCES.

        Returns
        -------
        pandas.DataFrame
            Filtered EXT SOURCES rows with columns ``FILENAME``, ``SVOLNO``,
            ``SMEMN``, ``TOPFST``, and ``TVOL``.
        """
        assert (smemn in dsns['SMEMN'].unique())
        dsns = dsns.loc[(dsns['TVOL'] == operation) & (dsns['TOPFST'] == opnid) & (dsns['SMEMN'] == smemn)]
        files = self.table('FILES').set_index('FTYPE')
        dsns.loc[:,'FILENAME'] = files.loc[dsns['SVOL'],'FILENAME'].values
        dsns = dsns[['FILENAME','SVOLNO','SMEMN','TOPFST','TVOL']]
        return dsns
    
        
    def initialize(self,name = None, default_output = 4,n=None,reach_ids = None, constituents = None):
        """Perform a full initialisation of the UCI binary-output configuration.

        Creates new BINO entries in the FILES table, configures BINARY-INFO
        output time codes for all operations, assigns GEN-INFO binary unit
        numbers, and standardises QUAL-ID names in QUAL-PROPS tables.  Calls
        :func:`setup_files`, :func:`setup_binaryinfo`, :func:`setup_geninfo`,
        and :func:`setup_qualid` in that order.

        Parameters
        ----------
        name : str or None, optional
            Prefix used when naming the new binary (``.hbn``) output files.
            Defaults to the UCI file stem when ``None``.
        default_output : int, optional
            Output time-code applied to all BINARY-INFO flags for all
            operations (default ``4`` = monthly).
        n : int or None, optional
            Number of binary output files to create.  When ``None`` and
            *reach_ids* is provided, defaults to ``len(reach_ids) // 2``.
            When both are ``None``, defaults to ``5``.
        reach_ids : list of int or None, optional
            Reach IDs for which hourly (time-code ``2``) output should be
            enabled.  When ``None``, hourly output is not set for any reach.
        constituents : list of str or None, optional
            Constituent keys that control which BINARY-INFO columns are set
            to hourly output for *reach_ids* (e.g. ``['Q', 'TSS', 'N']``).
            Defaults to ``['Q', 'WT', 'TSS', 'N', 'TKN', 'OP', 'BOD']``
            when ``None``.
        """
        
        if name is None:
            name = self.name
        
        if constituents is None:
            constituents = ['Q','WT','TSS','N','TKN','OP','BOD']

        if n is None and reach_ids is not None:
            n = int(len(reach_ids)/2)
        else:
            n = 5

        # Note that the order of these function calls matters
        setup_files(self,name,n)
        setup_binaryinfo(self,default_output = default_output,reach_ids = reach_ids,constituents = constituents)
        setup_geninfo(self)
        setup_qualid(self)

    def initialize_binary_info(self,default_output = 4,reach_ids = None,constituents = None):
        """Initialise only the BINARY-INFO and GEN-INFO tables.

        A lighter-weight alternative to :meth:`initialize` that skips FILES
        table setup and QUAL-ID standardisation.  Calls
        :func:`setup_binaryinfo` followed by :func:`setup_geninfo`.

        Parameters
        ----------
        default_output : int, optional
            Output time-code applied to all BINARY-INFO flags (default ``4``
            = monthly).
        reach_ids : list of int or None, optional
            Reach IDs for which hourly (time-code ``2``) output is enabled.
            When ``None``, hourly output is not set for any reach.
        constituents : list of str or None, optional
            Constituent keys controlling which BINARY-INFO columns are set
            to hourly output for *reach_ids*.  Defaults to
            ``['Q', 'WT', 'TSS', 'N', 'TKN', 'OP', 'BOD']`` when ``None``.
        """
        if constituents is None:
            constituents = ['Q','WT','TSS','N','TKN','OP','BOD']
        setup_binaryinfo(self,default_output = default_output,reach_ids = reach_ids,constituents=constituents)
        setup_geninfo(self)

    
    def build_targets(self):
        """Build a calibration target table from PERLND land covers.

        Uses ``self.opnid_dict['PERLND']`` together with the SCHEMATIC table
        to compute the total contributing area for each unique land-cover
        type.  The result is a summary DataFrame suitable for calibration
        target specification.

        Returns
        -------
        pandas.DataFrame
            One row per unique land-cover type with columns:

            * ``uci_name`` – LSID string from GEN-INFO.
            * ``lc_number`` – integer land-cover index.
            * ``area`` – total area (sum of AFACTR values from SCHEMATIC).
            * ``npsl_name`` – empty string placeholder for an external name.
            * ``TSS``, ``N``, ``TKN``, ``OP``, ``BOD`` – empty string
              placeholders for constituent calibration targets.
            * ``dom_lc`` – ``1`` for the land cover with the largest area,
              ``pd.NA`` for all others.
        """  
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


#TODO: More conveince methods that should probably be in a separate module

def run_model(uci_file, wait_for_completion=True):
    """Run the WinHSPF executable for a given UCI file.

    Resolves the path to ``WinHspfLt.exe`` relative to this package's
    ``bin`` directory and launches it as a subprocess.

    Parameters
    ----------
    uci_file : pathlib.Path
        Path to the UCI file to pass as the model input.
    wait_for_completion : bool, optional
        When ``True`` (default), block until the model process finishes
        (uses :func:`subprocess.run`).  When ``False``, launch the
        process in the background (uses :class:`subprocess.Popen`).
        On Windows, ``CREATE_NO_WINDOW`` is applied to suppress a console
        window when running in the background.
    """
    
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

def get_filepaths(uci,file_extension):
    """Return file paths from a UCI FILES table matching the given extension.

    Module-level counterpart to :meth:`UCI.get_filepaths`.

    Parameters
    ----------
    uci : UCI
        Loaded UCI object whose FILES table will be queried.
    file_extension : str
        File extension to filter by, including the leading dot
        (e.g. ``'.wdm'``).  The comparison is case-insensitive.

    Returns
    -------
    list of pathlib.Path
        Absolute paths constructed by joining each matching filename with
        the directory that contains the UCI file.
    """
    filepaths = files.loc[(files['FILENAME'].str.endswith(file_extension.lower())) |  (files['FILENAME'].str.endswith(file_extension.upper())),'FILENAME'].to_list()
    filepaths = [uci.filepath.parent.joinpath(filepath) for filepath in filepaths]
    return filepaths



def setup_files(uci,name,n = 5):
    """Initialise the FILES table with new binary output (BINO) entries.

    Performs the following operations in order:

    1. Strips directory paths from existing ``.wdm``, ``.ech``, ``.out``,
       and ``.hbn`` filenames, keeping only the bare filename.
    2. Removes any ``.plt`` entries.
    3. Removes all existing BINO entries.
    4. Selects *n* unique unit numbers (starting from 15) not already used
       by other FILES UNIT numbers or PLTGEN PLOTFL numbers.
    5. Appends *n* new BINO rows with filenames ``<name>-0.hbn``,
       ``<name>-1.hbn``, … and the chosen unit numbers.

    Parameters
    ----------
    uci : UCI
        The UCI object whose FILES table will be modified in-place.
    name : str
        Base name used to construct new binary output filenames.
    n : int, optional
        Number of new BINO entries to create (default ``5``).
    """

    if 'PLTGEN' in uci.block_names():
        pltgen_nums = uci.table('PLTGEN','PLOTINFO')['PLOTFL'].tolist()
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
    invalid = table['UNIT'].dropna().to_list() + pltgen_nums
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
    """Assign binary output unit numbers to GEN-INFO tables.

    Reads the BINO unit numbers from the FILES table and distributes all
    operation IDs (for RCHRES, PERLND, and IMPLND) evenly across the
    available BINO files according to each BINARY-INFO time-code value.
    Updates the ``BUNITE`` column (RCHRES) or ``BUNIT1`` column
    (PERLND/IMPLND) in the corresponding GEN-INFO table.

    Parameters
    ----------
    uci : UCI
        The UCI object whose GEN-INFO tables will be modified in-place.
        The FILES and BINARY-INFO tables must already be configured (e.g.
        via :func:`setup_files` and :func:`setup_binaryinfo`).
    """
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




def setup_binaryinfo(uci,default_output = 4,reach_ids = None,constituents = None):
    """Set BINARY-INFO output time codes for all operations.

    Applies *default_output* to every BINARY-INFO flag column for PERLND,
    IMPLND, and RCHRES.  If *reach_ids* is provided, additionally sets
    hourly output (time-code ``2``) for the flag columns associated with
    each constituent in *constituents* for the specified reaches.

    Parameters
    ----------
    uci : UCI
        The UCI object whose BINARY-INFO tables will be modified in-place.
    default_output : int, optional
        Time-code written to all BINARY-INFO flag columns (default ``4``
        = monthly).
    reach_ids : list of int or None, optional
        RCHRES operation IDs for which hourly output is enabled.  When
        ``None``, no hourly overrides are applied.
    constituents : list of str or None, optional
        Constituent keys used to look up the BINARY-INFO columns that
        should be set to hourly output for *reach_ids*.  Supported keys:
        ``'Q'``, ``'TSS'``, ``'WT'``, ``'N'``, ``'TKN'``, ``'OP'``,
        ``'BOD'``, ``'TP'``.  When ``None`` and *reach_ids* is provided,
        all relevant columns are set to hourly.

    Notes
    -----
    The mapping from constituent key to BINARY-INFO column name(s) is
    defined internally via ``CONSTITUENT_MAP``.
    """
    CONSTITUENT_MAP = {'Q': ['HYDRPR'],
                        'TSS': ['SEDPR'],
                        'WT': ['HEATPR'],
                        'N': ['OXRXPR','NUTRPR','PLNKPR'],
                        'TKN': ['OXRXPR','NUTRPR','PLNKPR'],
                        'OP': ['OXRXPR','NUTRPR','PLNKPR'],
                        'BOD': ['OXRXPR','NUTRPR','PLNKPR'],
                        'TP': ['OXRXPR','NUTRPR','PLNKPR']}
    
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
        if constituents is None:
             uci.update_table(2,'RCHRES','BINARY-INFO',0,columns = ['SEDPR','OXRXPR','NUTRPR','PLNKPR','HEATPR','HYDRPR'],opnids = reach_ids,operator = 'set')
        else:
            for constituent in constituents:
                uci.update_table(2,'RCHRES','BINARY-INFO',0,columns = CONSTITUENT_MAP[constituent],opnids = reach_ids,operator = 'set')

def setup_qualid(uci):
    """Standardise QUAL-ID names in QUAL-PROPS tables.

    Sets the ``QUALID`` column in the PERLND and IMPLND QUAL-PROPS tables
    (indices 0–3) to the standard names ``'NH3+NH4'``, ``'NO3'``,
    ``'ORTHO P'``, and ``'BOD'`` respectively.

    Parameters
    ----------
    uci : UCI
        The UCI object whose QUAL-PROPS tables will be modified in-place.
    """
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




def chuck(adjustment,table):
    """Adjust monthly concentration table values using min/max neighbour logic.

    For each month index *i*, if ``adjustment[i] > 1``, the *minimum* of the
    adjacent pair ``(table[:,i], table[:,i+1])`` is increased by the
    adjustment factor.  If ``adjustment[i] < 1``, the *maximum* of the pair
    is decreased.  Months with ``adjustment[i] == 1`` are left unchanged.
    When a cell is updated multiple times it is averaged over the update
    count.

    A circular "dummy" column equal to the first column is appended before
    processing so that December wraps around to January.

    Parameters
    ----------
    adjustment : array-like of float
        One multiplier per month (length 12).  Values greater than ``1``
        increase the lower neighbour; values less than ``1`` decrease the
        upper neighbour.
    table : pandas.DataFrame
        Monthly concentration table with shape ``(n_opnids, 12)``.  The
        DataFrame index corresponds to operation IDs.

    Returns
    -------
    pandas.DataFrame
        Adjusted concentration table with the same shape and index as the
        input *table*.
    """
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




# Expanding opnid-opnid in tables
def format_opnids(table,valid_opnids):
    """Expand range-style OPNID entries and filter to valid operation IDs.

    UCI tables sometimes encode a range of operation IDs as a single row with
    an OPNID value like ``'1 5'`` (meaning IDs 1 through 5 inclusive).  This
    function expands such rows into one row per ID, filters the result to only
    those IDs present in *valid_opnids*, and sets OPNID as the DataFrame index.

    Parameters
    ----------
    table : pandas.DataFrame
        Parsed table data that includes an ``OPNID`` column.  Comment rows
        (where ``OPNID`` is empty) are preserved.
    valid_opnids : list of int
        The set of active operation IDs for the block being processed
        (typically one of the per-operation lists from ``UCI.valid_opnids``).

    Returns
    -------
    pandas.DataFrame
        Expanded and filtered table with ``OPNID`` (integer) as the index.
    """
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

def expand_extsources(data,valid_opnids):
    """Expand range-style EXT SOURCES entries and filter to valid operation IDs.

    EXT SOURCES rows may specify a range of target operation IDs via
    ``TOPFST`` and ``TOPLST`` columns.  This function expands such rows into
    one row per operation ID, sets ``TOPLST`` to ``pd.NA`` for expanded rows,
    and then removes rows for operation IDs not present in *valid_opnids* for
    their respective ``TVOL`` operation.

    Parameters
    ----------
    data : pandas.DataFrame
        Parsed EXT SOURCES table containing at minimum the columns
        ``TOPFST``, ``TOPLST``, and ``TVOL``.
    valid_opnids : dict
        Mapping of operation name (e.g. ``'PERLND'``) to a list of active
        integer operation IDs (typically ``UCI.valid_opnids``).

    Returns
    -------
    pandas.DataFrame
        Expanded and filtered EXT SOURCES table with a reset integer index.
    """
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
    df = pd.concat([a.loc[:insertion_point], b, a.loc[insertion_point:]])
    if reset_index: df = df.reset_index(drop=True)
    return df
    



def keep_valid_opnids(table,opnid_column,valid_opnids):
    """Filter a table to rows with valid operation IDs, preserving comment rows.

    For each operation in *valid_opnids*, keeps rows where the value in
    *opnid_column* matches that operation's active ID list and ``TVOL``
    equals the operation name.  Comment rows (non-empty ``comments`` column)
    are always retained regardless of OPNID.

    Parameters
    ----------
    table : pandas.DataFrame
        Table to filter.  Must contain *opnid_column*, ``TVOL``, and
        ``comments`` columns.
    opnid_column : str
        Name of the column containing operation IDs (e.g. ``'TOPFST'``).
    valid_opnids : dict
        Mapping of operation name to list of active integer operation IDs.

    Returns
    -------
    pandas.DataFrame
        Filtered table sorted by original row order with a reset integer
        index.
    """
    valid_indexes = [table.index[(table[opnid_column].isin(valid_opnids[operation])) & (table['TVOL'] == operation)] for operation in valid_opnids.keys()]
    valid_indexes.append(table.index[table['comments'] != ''])
    table = pd.concat([table.loc[valid_index] for valid_index in valid_indexes])
    table = table.sort_index().reset_index(drop=True)
    return table


def  RUN_comments(lines):
    """Extract comment lines that appear before the ``RUN`` keyword.

    Scans *lines* for the ``'RUN'`` sentinel, then collects any lines
    containing ``'***'`` that appear before it.  Stops collecting as soon
    as a non-comment, non-blank line is encountered.

    Parameters
    ----------
    lines : list of str
        UCI file lines as returned by :func:`reader` (no blank lines).

    Returns
    -------
    list of str
        Comment lines (those containing ``'***'``) found before ``'RUN'``.
    """
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

# Functions for converting the uci text file into a dictionary structure made up of my custom Table class
def reader(filepath):
    """Read a UCI file and return its non-blank, properly-trimmed lines.

    Opens the file with UTF-8 encoding (ignoring undecodable bytes) and
    processes each line as follows:

    * Blank lines are skipped.
    * Comment lines (containing ``'***'``) are kept as-is after
      right-stripping whitespace.
    * All other lines are truncated to 80 characters and right-stripped.

    Parameters
    ----------
    filepath : str or pathlib.Path
        Path to the UCI file.

    Returns
    -------
    list of str
        Cleaned lines from the file, with blank lines removed.
    """
    
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
                                              
def decompose_perlands(metzones,landcovers):
    """Decompose perland IDs into (metzone, landcover) component tuples.

    Creates a dictionary keyed by the integer sum ``metzone + landcover``
    (the combined perland ID used internally by HSPF) mapping to the
    constituent ``(metzone, landcover)`` tuple.

    Parameters
    ----------
    metzones : iterable of int or str
        Meteorological zone IDs.
    landcovers : iterable of int or str
        Land-cover type IDs.

    Returns
    -------
    dict
        Mapping of ``int(metzone) + int(landcover)`` to
        ``(int(metzone), int(landcover))`` tuples for every combination of
        *metzones* and *landcovers*.
    """
    perlands = {}
    for metzone in metzones:
        metzone = int(metzone)
        for landcover in landcovers:
            landcover = int(landcover)
            perlands[metzone+landcover] = (metzone,landcover)
    return perlands

def split_number(s):
    """Split trailing digits from a string.

    Parameters
    ----------
    s : str
        Input string, optionally ending with one or more digit characters.

    Returns
    -------
    head : str
        The leading non-digit portion of *s*, right-stripped of whitespace.
    tail : str
        The trailing digit substring (empty string if *s* has no trailing
        digits).

    Examples
    --------
    >>> split_number('GEN-INFO3')
    ('GEN-INFO', '3')
    >>> split_number('GLOBAL')
    ('GLOBAL', '')
    """
    head = s.rstrip('0123456789')
    tail = s[len(head):]
    return head.strip(), tail

#TODO merge the get_blocks and build_uci into a single function to reduce number of for loops
def get_blocks(lines):
    """Identify block start and end line indices in a UCI file.

    Iterates through *lines* in reverse to locate ``'END <BLOCKNAME>'`` and
    matching ``'<BLOCKNAME>'`` sentinel lines for each top-level block
    defined in ``parseTable``.  Only recognised block names (present in the
    ``'block'`` column of ``parseTable``) are processed.

    Parameters
    ----------
    lines : list of str
        UCI file lines as returned by :func:`reader`.

    Returns
    -------
    dict
        Mapping of block name (str) to a sub-dict ``{'indcs': [end_idx,
        start_idx]}`` where *end_idx* is the line index of ``'END
        <BLOCKNAME>'`` and *start_idx* is the line index of ``'<BLOCKNAME>'``
        (i.e. the block opener).
    """
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
    """Parse UCI line data into a dict of :class:`~hspf.parser.parsers.Table` objects.

    Uses :func:`get_blocks` to locate block boundaries, then iterates within
    each block (in reverse) to identify individual sub-tables by their
    ``END <TABLE>`` / ``<TABLE>`` sentinel pairs.  Two categories of blocks
    are handled:

    * **Simple blocks** (``table_name = 'na'`` in ``parseTable``): the entire
      block content is stored as a single Table.
    * **Complex blocks**: each named sub-table is stored separately.

    Tables are stored with ``data = None``; parsing is deferred to the first
    call of :meth:`UCI.table`.

    Duplicate table names within the same block are disambiguated by a
    zero-based ``table_id`` counter assigned after reversing the parse order
    to match top-to-bottom appearance in the file.

    Parameters
    ----------
    lines : list of str
        UCI file lines as returned by :func:`reader`.

    Returns
    -------
    dict
        Mapping of ``(block_name, table_name, table_id)`` tuples to
        :class:`~hspf.parser.parsers.Table` objects.
    """
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

