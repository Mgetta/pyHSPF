import numpy as np
import pandas as pd
from hspf.model.parsers import Table
from hspf.model.graph import reachNetwork

from hspf.model.UCI.parsing import reader, get_blocks, RUN_comments, build_uci
from hspf.model.UCI.edits import format_opnids, expand_extsources
from hspf.model.UCI.views import simulated_opnids, infer_metzones, get_filepaths, get_dsns, targets, masslinks
from pathlib import Path


class UciDocument:
    def __init__(self, filepath):
        self.filepath = filepath
        self.name = Path(filepath).stem
        self.lines = reader(filepath)
        self.blocks = get_blocks(self.lines)
        self.run_comments = RUN_comments(self.lines)
        self.uci = build_uci(self.lines) # UCI converted into a nested dictionary. # Could convert into a class with only tables? 
                # Require to get valid opnids - Business rule

    @property
    def simulated_opnids(self):
        return simulated_opnids(self)

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
                table.replace(format_opnids(table.data,self.simulated_opnids[block]))
            elif block in ['EXT SOURCES','NETWORK']:
                table.replace(expand_extsources(table.data,self.simulated_opnids))
            
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
        self.merge_lines()
        self._write(new_uci_path) 


