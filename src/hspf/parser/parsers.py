# -*- coding: utf-8 -*-
"""
Created on Fri Oct  7 12:13:23 2022

@author: mfratki
"""

from abc import abstractmethod
from multiprocessing.util import info
import numpy as np
import pandas as pd
from pathlib import Path
import math

# Read in table used to parse UCI file #RespectRespec
parseTable = pd.read_csv(Path(__file__).parent.parent/'data/ParseTable.csv',
                          dtype = {'width': 'Int64',
                                  'start': 'Int64',
                                  'stop': 'Int64',
                                  'space': 'Int64'})                                  
# parseTable = pd.read_csv('C:/Users/mfratki/Documents/GitHub/hspf_tools/parser/ParseTable.csv',
#                             dtype = {'width': 'Int64',
#                                       'start': 'Int64',
#                                       'stop': 'Int64',
#                                       'space': 'Int64'})
# Parser ipmlementation
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


# table header rules

# standard: line[6:].strip()
# mass-link: line[6:].strip() + '     ' + str(number) #5 spaces 
# ftables: line[6:].strip() + '    ' + str(number) #4 spaces
# month-data: line[6:].strip() + '     ' + str(number) #5 spaces
# def format_table_name(block,table_name):
#     text,number = split_number(table_name.strip())
#     if block == 'MASS-LINK':
#         header = text + ' '*5 + str(number)
#         footer = text + ' ' + str(number)
#         name = str(number)
#     elif block == 'FTABLES':
#         header = text + ' '*4 + str(number)
#         footer = text + str(number)
#         name = str(number)
#     elif block == 'MONTH-DATA':
#         header = text + ' '*5 + str(number)
#         footer = text + ' ' + str(number)
#         name = str(number)
#     else:
#         header = text+number
#         footer = text+number
#         name = text+number
#     return header,footer,text,name


class defaultParser(Parser):
    def parse(block,table,lines):
        raise NotImplementedError()
    
    def write(block,table,lines):
        raise NotImplementedError()

class standardParser(Parser):
    def parse(block,table_name,table_lines):
        column_names,dtypes,starts,stops = delimiters(block,table_name)
        table = parse_lines(table_lines,starts,stops,dtypes)
        table = column_dtypes(table,dtypes,column_names) 
        return table

    def write(block,table_name,table):
        # Assumes all tables start with two indented spaces
        # spaces = '  '
        # if table_name == 'na':
        #     spaces = ''
        #table[table.columns[0]] = spaces + table[table.columns[0]].astype(str)
        column_names,dtypes,starts,stops = delimiters(block,table_name)
        table_list = table.values.tolist() #This conversion will likely cause a bug
        table_lines = ['']*len(table_list)
        for index,line in enumerate(table_list):
            if line[-1] == '':
                table_lines[index] = format_line(line,starts,stops,dtypes)
            else:
                table_lines[index] = line[-1]
                
        return table_lines

class operationsParser(Parser):
    def parse(block,table_name,table_lines):
        column_names,dtypes,starts,stops = delimiters(block,table_name)
        table = parse_lines(table_lines,starts,stops,dtypes)
        table = column_dtypes(table,dtypes,column_names)
        table = table.set_index('OPNID')
        return table

    def write(block,table_name,table):
        # Assumes all tables start with two indented spaces
        # spaces = '  '
        # if table_name == 'na':
        #     spaces = ''
        #table[table.columns[0]] = spaces + table[table.columns[0]].astype(str)
        table = table.reset_index()
        column_names,dtypes,starts,stops = delimiters(block,table_name)
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

class ftableParser(Parser):
    def parse(block,table_name,table_lines):
        column_names,dtypes,starts,stops = delimiters('FTABLES','FTABLE')
        table = parse_lines(table_lines,starts,stops,dtypes)
        table = column_dtypes(table,dtypes,column_names) 
        return table

    def write(block,table_name,table):
        # Assumes all tables start with two indented spaces
        # spaces = '  '
        # if table_name == 'na':
        #     spaces = ''
        #table[table.columns[0]] = spaces + table[table.columns[0]].astype(str)
        column_names,dtypes,starts,stops = delimiters('FTABLES','FTABLE')
        table_list = table.values.tolist() #This conversion will likely cause a bug
        table_lines = ['']*len(table_list)
        for index,line in enumerate(table_list):
            if line[-1] == '':
                table_lines[index] = format_line(line,starts,stops,dtypes)
            else:
                table_lines[index] = line[-1]
                
        return table_lines

class monthdataParser(Parser):
    def parse(block,table_name,table_lines):
        column_names,dtypes,starts,stops = delimiters('MONTH-DATA','MONTH-DATA')
        table = parse_lines(table_lines,starts,stops,dtypes)
        table = column_dtypes(table,dtypes,column_names) 
        return table
    
    def write(block,table_name,table):
        # Assumes all tables start with two indented spaces
        # spaces = '  '
        # if table_name == 'na':
        #     spaces = ''
        #table[table.columns[0]] = spaces + table[table.columns[0]].astype(str)
        column_names,dtypes,starts,stops = delimiters('MONTH-DATA','MONTH-DATA')
        table_list = table.values.tolist() #This conversion will likely cause a bug
        table_lines = ['']*len(table_list)
        for index,line in enumerate(table_list):
            if line[-1] == '':
                table_lines[index] = format_line(line,starts,stops,dtypes)
            else:
                table_lines[index] = line[-1]
                
        return table_lines
        
class masslinkParser(Parser):
    def parse(block,table_name,table_lines):
        column_names,dtypes,starts,stops = delimiters('MASS-LINK','MASS-LINK')
        table = parse_lines(table_lines,starts,stops,dtypes)
        table = column_dtypes(table,dtypes,column_names) 
        return table

    def write(block,table_name,table):
        # Assumes all tables start with two indented spaces
        # spaces = '  '
        # if table_name == 'na':
        #     spaces = ''
        #table[table.columns[0]] = spaces + table[table.columns[0]].astype(str)
        column_names,dtypes,starts,stops = delimiters('MASS-LINK','MASS-LINK')
        table_list = table.values.tolist() #This conversion will likely cause a bug
        table_lines = ['']*len(table_list)
        for index,line in enumerate(table_list):
            if line[-1] == '':
                table_lines[index] = format_line(line,starts,stops,dtypes)
            else:
                table_lines[index] = line[-1]
                
        return table_lines       

class globalParser(Parser):
    def parse(block,table_name,table_lines):
        
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
        return df
    
    def write(block,table_name,table):
        raise NotImplementedError()

class specactionsParser(Parser):
    def parse(block,table,lines):
        raise NotImplementedError()

    def write(block,table,lines):
        raise NotImplementedError()

class externalsourcesParser():
    def parse(block,table,lines):
        raise NotImplementedError()

    def write(block,table,lines):
        raise NotImplementedError()

parserSelector = {'GLOBAL':globalParser,
                'FILES':standardParser,
                'OPN SEQUENCE':opnsequenceParser,
                'PERLND':operationsParser,
                'IMPLND':operationsParser,
                'RCHRES':operationsParser,
                'COPY':operationsParser,
                'PLTGEN':defaultParser,
                'DISPLY':defaultParser,
                'DURANL':defaultParser,
                'GENER':operationsParser,
                'MUTSIN':defaultParser,
                'BMPRAC':defaultParser,
                'REPORT':defaultParser,
                'FTABLES':ftableParser,
                'EXT SOURCES':standardParser,
                'NETWORK':standardParser,
                'SCHEMATIC':standardParser,
                'MASS-LINK': masslinkParser,
                'EXT TARGETS':standardParser,
                'PATHNAMES':defaultParser,
                'FORMATS':defaultParser,
                'SHADE':defaultParser,
                'SPEC-ACTIONS':specactionsParser,
                'MONTH-DATA':monthdataParser,
                'CATEGORY':defaultParser}

# Parsing functions
# for parsing individual tables using the ParseTabl csv
def delimiters(block_name,table_name):
    parse_info =  parseTable[(parseTable['block'] == block_name) & (parseTable['table'] == table_name)]
    names = parse_info['column'].astype(str).to_list()
    dtypes = parse_info['dtype'].astype(str).to_list()
    starts = parse_info['start'].astype(int).to_list()
    stops = parse_info['stop'].astype(int).to_list()
    
    # Add comments info
    
    names.append('comments')
    dtypes.append('C')
    starts.append(stops[-1])
    stops.append(stops[-1])
    
    return names, dtypes,starts,stops


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


def parse_line(line,starts,stops,dtypes):
    values = []
    for start,stop,dtype in zip(starts,stops,dtypes):
        value = line[start:stop]
        if dtype == 'C':
            value = str(value).strip()
        elif dtype =='I':
            try:
                value = int(value)
            except ValueError:
                value = pd.NA
        else:
            try:
                value = float(value)
            except ValueError:
                value = np.nan
        values.append(value)
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


def format_line(line,starts,stops,dtypes):
    formatted_line = list(' '*np.max(stops))
    for start,stop,value,dtype in zip(starts,stops,line,dtypes):
        width = stop-start
        if pd.isna(value):
            formatted_line[start:stop] = list(' '*width) # Add the needed spaces
        elif isinstance(value,bool): # Has to come first since False evaluates to true in next if statement
           formatted_line[start:stop] = list(' '*width) # Add the needed spaces
        elif value == 'False':
           formatted_line[start:stop] = list(' '*width)
        elif value is np.nan:
           formatted_line[start:stop] = list(' '*width)            
        elif isinstance(value, (int,str)): # Right justify integers?
            if dtype == 'I':
                value = str(value)
                len_value = len(value)
                assert(len_value <= width) # check for integer overflow
                formatted_line[start:stop] =  list(' '*(width-len(str(value)))+str(value))
            else: # Left justify strings?
                formatted_line[start:stop] = list(str(value) + ' '*(width-len(str(value))))
        else: 
           formatted_line[start:stop] = list(format_number(value,width))
           
    return ''.join(formatted_line)

