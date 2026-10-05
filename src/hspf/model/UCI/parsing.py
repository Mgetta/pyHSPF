
from abc import ABC, abstractmethod
import numpy as np
import pandas as pd
from typing import Union
from pathlib import Path
import math

from hspf.model.UCI.schema import resolve_schema
parseTable = pd.read_csv(Path(__file__).parent.parent.parent/'data/ParseTable.csv',
                          dtype = {'width': 'Int64',
                                  'start': 'Int64',
                                  'stop': 'Int64',
                                  'space': 'Int64'})


       

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


class Parser:
    @abstractmethod      
    def parse(self):
        pass

    @abstractmethod      
    def write(self):
        pass


class Table():
    def __init__(self,block,name,table_id = 0,activity = None,dtypes = None,columns = None,widths = None):
        self.name = name
        self.id = table_id
        self.activity = activity
        self.block = block
        self.dtypes = dtypes
        self.columns = columns
        self.widths = widths
        self.data = None
        self.comments = None
        self.lines = None
        self.header = None
        self.footer = None
        self.supplemental = False
        
    
        self.parser = parserSelector[self.block]
        #self.updater = Updater
    
    def _delimiters(self):
        return delimiters(self.block,self.name)
    
    def parse(self):
        self.data = self.parser.parse(self.block,self.name,self.lines)
        
    def write(self): # specify values
        self.lines = self.parser.write(self.block,self.name,self.data)        
    
    def replace(self,data): #replace an entire table 
        self.data = data.copy()
        self.write()
    
    def set_value(self,rows,columns,value,axis = 0):
        self.data.loc[rows,columns] = value
        self.write()
    
    def mul(self,rows,columns,value,axis = 0):
        self.data.loc[rows,columns] = self.data.loc[rows,columns].mul(value,axis)
        self.write()
        
    def add(self,rows,columns,value,axis = 0):
        self.data.loc[rows,columns] = self.data.loc[rows,columns].add(value,axis)
        self.write()
        
    def sub(self,rows,columns,value,axis = 0 ):
        self.data.loc[rows,columns] = self.data.loc[rows,columns].sub(value,axis)
        self.write()
        
    def div(self,rows,columns,value,axis = 0):
        self.data.loc[rows,columns] = self.data.loc[rows,columns].div(value,axis)
        self.write()


class defaultParser(Parser):
    def parse(block,table,lines):
        raise NotImplementedError()
    
    def write(block,table,lines):
        raise NotImplementedError()

class standardParser(Parser):
    def parse(block,table_name,table_lines):
        schema = resolve_schema(block, table_name) #
        column_names = schema.column_names #
        dtypes =schema.column_dtypes #
        starts = schema.column_starts #
        stops = schema.column_stops #
        table = parse_lines(table_lines,starts,stops,dtypes)
        table = column_dtypes(table,dtypes,column_names) 
        return table

    def write(block,table_name,table):
        # Assumes all tables start with two indented spaces
        # spaces = '  '
        # if table_name == 'na':
        #     spaces = ''
        #table[table.columns[0]] = spaces + table[table.columns[0]].astype(str)
        schema = resolve_schema(block, table_name) #
        column_names = schema.column_names #
        dtypes = schema.column_dtypes #
        starts = schema.column_starts #
        stops = schema.column_stops #
        table_list = table.values.tolist() #This conversion will likely cause a bug
        table_lines = ['']*len(table_list)
        for index,line in enumerate(table_list):
            if line[-1] == '':
                table_lines[index] = format_line(line,starts,stops,dtypes)
            else:
                table_lines[index] = line[-1]
                
        return table_lines

class opnsequenceParser(Parser):
    def parse(block,table_name,table_lines):
        '''
        Function for parsing the Open Sequence block of the uci file. This block
        contains all operation ids represented in the model which is neccesary for
        formatting tables that have an x-x mapping. There fore this block MUST be
        parsed when first reading a UCI file

        Parameters
        ----------
        lines : List
            List containg each line in the uci file with blank lines and comments
            removed.

        Returns
        -------
        pandas DataFrame
            Data frame providing informatio on the operaiton, id number and temporal
            resolution of the model in minutes.

        '''
        ops = {'PERLND', 'IMPLND', 'RCHRES', 'COPY', 'GENER'}
        lst = []
        for line in table_lines:
            if '***' in line:
                #   columns:  ['OPERATION', 'SEGMENT', 'INDELT_minutes','comments']
                #   Assumed dtypes: (string,'Int64','float64',string] 
                #   NaN values {'I':-1,'C':'','R':np.nan}
                lst.append(('',-1,np.nan,line)) #  
            else:
                tokens = line.split()
                if tokens[0] == 'INGRP' and tokens[1] == 'INDELT':
                    s = tokens[2].split(':')
                    indelt = int(s[0]) if len(s) == 1 else 60 * int(s[0]) + int(s[1])
                elif tokens[0] in ops:
                    #s = f'{tokens[0][0]}{int(tokens[1]):03d}' # Original RESPEC method
                    s = int(tokens[1])
                    lst.append((tokens[0], s, indelt,''))
                    
        return pd.DataFrame(lst, columns = ['OPERATION', 'SEGMENT', 'INDELT_minutes','comments'])



    def write(block,table,lines):
        raise NotImplementedError()

class globalParser(Parser):
    def parse(block,table_name,table_lines):
        table_lines = [line for line in table_lines if '***' not in line]
        data = {
            'description' : table_lines[0].strip(),
            'start_date' : table_lines[1].split('END')[0].split()[1],
            'start_hour' :  int(table_lines[1].split('END')[0].split()[2][:2])-1,
            'end_date' : table_lines[1].strip().split('END')[1].split()[0],
            'end_hour' : int(table_lines[1].strip().split('END')[1].split()[1][:2])-1,
            'echo_flag1' : int(table_lines[2].split()[-2]),
            'echo_flag2' : int(table_lines[3].split()[-1]),
            'units_flag' : int(table_lines[3].split()[5]),
            'resume_flag': int(table_lines[3].split()[1]),
            'run_flag': int(table_lines[3].split()[3]) 
        }
        df = pd.DataFrame([data])
        df['comments'] = ''
        return df
    
    def write(block,table_name,table):
        raise NotImplementedError()

parserSelector = {'GLOBAL':globalParser,
                'FILES':standardParser,
                'OPN SEQUENCE':opnsequenceParser,
                'PERLND':standardParser,
                'IMPLND':standardParser,
                'RCHRES':standardParser,
                'COPY':standardParser,
                'PLTGEN':standardParser,
                'DISPLY':defaultParser,
                'DURANL':defaultParser,
                'GENER':standardParser,
                'MUTSIN':defaultParser,
                'BMPRAC':defaultParser,
                'REPORT':defaultParser,
                'FTABLES':standardParser,
                'EXT SOURCES':standardParser,
                'NETWORK':standardParser,
                'SCHEMATIC':standardParser,
                'MASS-LINK': standardParser,
                'EXT TARGETS':standardParser,
                'PATHNAMES':defaultParser,
                'FORMATS':defaultParser,
                'SHADE':defaultParser,
                'SPEC-ACTIONS':defaultParser,
                'MONTH-DATA':standardParser,
                'CATEGORY':defaultParser}


def parse_lines2(lines,starts,stops,dtypes):
    comments = []
    table = []
    for index,line in enumerate(lines):
        if '***' in line:
            comments.append(line)
            if index+1 == len(lines): # Cases where the table ends with comments
                comments = '\n'.join(comments)
                table[-1][-1] = '/n/'.join([table[-1][-1],comments]) 
                # '/n/ to separate comments above a line and comments below a line for cases 
                #      where the table ends with comments below a single valid line
        else:
            table.append(parse_line(line,starts,stops,dtypes))
            
            comments = '\n'.join(comments)
            if comments != '':
                comments = '/n/'.join([comments,''])
                
            table[-1][-1] = comments
            comments = []
    return table
    

def parse_lines(lines,starts,stops,dtypes):
    defaults = {'I':pd.NA,'C':'','R':np.nan}
    nan_row = [defaults[dtype] for dtype in dtypes]
    table = []
    for line in lines:
        if '***' in line:
            row = nan_row.copy()
            row[-1] = line
            table.append(row)
        else:
            row = parse_line(line,starts,stops,dtypes)
            table.append(parse_line(line,starts,stops,dtypes))
    return table


def parse_line(line, starts, stops, dtypes):
    values = []
    for start, stop, dtype in zip(starts, stops, dtypes):
        text = line[start:stop].strip()
        
        if dtype == 'C':
            values.append(text)
        elif dtype == 'I':
            values.append(int(text) if text else pd.NA)
        elif dtype == 'R':
            values.append(float(text) if text else np.nan)
            
    return values

    
def column_dtypes(table,dtypes,names):
    convert = {'I':'Int64','C':'string','R':'float64'}
    col_dtypes = {}
    for dtype,name in zip(dtypes,names):
        col_dtypes[name] = convert[dtype]
        
    table = pd.DataFrame(table,columns = names)
    table = table.astype(dtype=col_dtypes)   
    return table




# Writing Functions
def magnitude(x):
    return int(math.log10(x))
    
def num_zeros(decimal):
    return math.inf if decimal == 0 else -math.floor(math.log10(abs(decimal))) - 1

def format_number(number,width):
    if number == 0:
        return ' '*(width-1) + '0'
    
    if pd.isna(number):
        return ' '*width
        
    '''
    Format numbers in the uci file. For both integer and floats. 
    Display the minimum number of characters (for visual purposes) with the highest precision
    Code breaks if widths dip below 2 but for floats I don't think hspf ever goes below 5?'

    '''
    assert(width > 2)
    
    sign = ''
    if number < 0:
        width = width-1
        sign = '-'
        number = number*-1
        
        
    if number < 1:
        chars = width 
        zeros = num_zeros(number) + 1
        if chars <= zeros: # can't represent number with given width
            chars = chars - 4 - 2
            if chars < 0:
                chars = 0
            string = f'{number:.{chars}E}'.replace("E-0","E-").split("E")
            string = string[0].strip('0').rstrip('.') + 'E' + string[1] 
            
            if len(string) > width: # Check once to see if scientific notation fits within width limitations
                string = '1E-9'
            if len(string) > width: # Check if minimum scientific notation width is still too long then use minimum standard notation value
                string = '.' + '0'*(width-2) + '1'      
        else:
            chars = width - 1#1 characcter must be allocated for the decimal point
            string = f'{number:.{chars}f}'.strip('0').rstrip('.')
                 
    else:        
        magnitude = int(math.log10(number)) + 1 #number of characters required for integer in standard notation
        if magnitude > width: #If there is integer overflow try using scientific notation
            chars = width - 4 - 1
            if chars < 0:
                chars = 0
            string = f'{number:.{chars}E}'.replace("E+0","E+").split("E")
            string = string[0].strip('0').rstrip('.') + 'E' + string[1]
            
            if len(string) > width: # Check once to see if scientific notation fits within width limitations
                string = '9E+9'
            if len(string) > width: # Check if minimum scientific notation width is still to long then use maximum integer value
                string = '9'*width        
        else: # subtract 1 from the width for the decimal character
            chars = width - magnitude  - 1
            if chars <= 0:
                string =  f'{number:.{0}f}'
            else:
                string = f'{number:.{chars}f}'.strip('0').strip('.')
    
    
    return ' '*(width - len(sign+string))+sign + string #' '*(width-len(string)) + string

# A conceptual simplification using Python's native formatting
def format_number_simplified(number, width):
    if pd.isna(number):
        return ' ' * width
    if number == 0:
        return '0'.rjust(width)
        
    # {:g} dynamically chooses between standard and scientific notation
    # based on the number's magnitude, attempting to use up to 'width-1' significant digits.
    text = f"{number:.{width-1}g}"
    
    # Optional: strip leading zero to save 1 character of width (0.15 -> .15)
    if text.startswith('0.'):
        text = text[1:]
    elif text.startswith('-0.'):
        text = '-' + text[2:]
        
    # Fallback if standard Python formatting still exceeds width
    if len(text) > width:
        # Revert to your custom overflow logic here
        pass 
        
    return text.rjust(width)



def format_line(line, starts, stops, dtypes):
    max_len = max(stops) if stops else 0
    formatted_line = [' '] * max_len
    
    for start, stop, value, dtype in zip(starts, stops, line, dtypes):
        width = stop - start
        
        # 1. Catch all null/empty variants immediately
        if pd.isna(value) or value is np.nan or value == 'False' or value is False:
            text = ' ' * width
            
        # 2. Format purely based on the intended Schema dtype
        elif dtype == 'C':
            text = str(value).ljust(width)  # Strings left-justified
        elif dtype == 'I':
            text = str(value).rjust(width)  # Integers right-justified
        elif dtype == 'R':
            text = format_number(value, width)
        else:
            text = ' ' * width
            
        # 3. Inject into the line (truncating to 'width' to guarantee no column overflow)
        formatted_line[start:stop] = list(text[:width])
        
    return ''.join(formatted_line)


# def format_line(line,starts,stops,dtypes):
#     formatted_line = list(' '*np.max(stops))
#     for start,stop,value,dtype in zip(starts,stops,line,dtypes):
#         width = stop-start
#         if pd.isna(value):
#             formatted_line[start:stop] = list(' '*width) # Add the needed spaces
#         elif isinstance(value,bool): # Has to come first since False evaluates to true in next if statement
#            formatted_line[start:stop] = list(' '*width) # Add the needed spaces
#         elif value == 'False':
#            formatted_line[start:stop] = list(' '*width)
#         elif value is np.nan:
#            formatted_line[start:stop] = list(' '*width)            
#         elif isinstance(value, (int,str)): # Right justify integers?
#             if dtype == 'I':
#                 value = str(value)
#                 len_value = len(value)
#                 assert(len_value <= width) # check for integer overflow
#                 formatted_line[start:stop] =  list(' '*(width-len(str(value)))+str(value))
#             else: # Left justify strings?
#                 formatted_line[start:stop] = list(str(value) + ' '*(width-len(str(value))))
#         else: 
#            formatted_line[start:stop] = list(format_number(value,width))
           
#     return ''.join(formatted_line)

