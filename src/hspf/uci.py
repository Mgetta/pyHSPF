# -*- coding: utf-8 -*-
"""
Created on Mon Jul 11 08:39:57 2022

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
#uci interface
class UCI():
    def __init__(self, filepath,infer_metzones = True):
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
        raise NotImplementedError()
    
                 
    def table(self,block,table_name = 'na',table_id = 0,drop_comments = True):
        # Dynamic parsing of tables when called by user
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
    
    def _table(self,block,table_name,table_id):
        return self.uci[(block,table_name,table_id)]
    
    def replace_table(self,table,block,table_name = 'na',table_id = 0): #replace an entire table 
        self.uci[(block,table_name,table_id)].replace(table)

    def table_lines(self,block,table_name = 'na',table_id = 0):
        return self.uci[(block,table_name,table_id)].lines.copy()
        
    def comments(block,table_name = None,table_id = 0): # comments of a table
        raise NotImplementedError()
        
    def table_names(self,block):
        return list(set([key[1] for key in list(self.uci.keys()) if key[0] == block]))
        
    def block_names(self): #blocks present in a particular uci file
        return set([key[0] for key in list(self.uci.keys())])
    
    def add_comment(self,comment):
        raise NotImplementedError()
                
    def update_table(self,value,operation,table_name,table_id,opnids = None,columns = None,operator = '*',axis = 0):
        # This should be moved up one layer as this is a user/business requirement. I would pass a Table object from this layer (data lyaer?) to the business layer, make changes, then pass it back down to this layer.
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
    
    def merge_lines(self): # write uci to a txt file
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
        # Update GLOBAL table with new start and end dates very janky implementation but not a priority.

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
        table_lines = self.table_lines('GLOBAL')  
        for index, line in enumerate(table_lines):
            if '***' in line: #in case there are comments in the global block
                continue
            elif line.strip().startswith('RUN INTERP OUTPT LEVELS'):
                table_lines[index] = f'  RUN INTERP OUTPT LEVELS    {flag1}    {flag2}'
            else:
                continue
        

        self.uci[('GLOBAL','na',0)].lines = table_lines


    def _write(self,filepath):
        with open(filepath, 'w') as the_file:
            for line in self.lines:    
                the_file.write(line+'\n')

    def add_parameter_template(self,block,table_name,table_id,column,parname = None,tpl_char = '~',opnids = None,single_template = True, group_id = ''):
        
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

    def write_tpl(self,tpl_char = '~',new_tpl_path = None):    
        if new_tpl_path is None:
            new_tpl_path = self.filepath.parent.joinpath(self.filepath.stem + '.tpl')
        self.merge_lines()
        self.lines.insert(0,'ptf ' + tpl_char)
        self._write(new_tpl_path)

    def write(self,new_uci_path):
        self.merge_lines()
        self._write(new_uci_path) 

    def _run(self,wait_for_completion=True):
        run_model(self.filepath, wait_for_completion=wait_for_completion)

    def update_bino(self,name):
        #TODO: Move up to busniess/presentation layer
        table = self.table('FILES',drop_comments = False) # initialize the table
        indexs = table[table['FTYPE'] == 'BINO'].index
        for index in indexs: 
            table.loc[index,'FILENAME'] = name + '-' + table.loc[index,'FILENAME'].split('-')[-1]          
        self.replace_table(table,'FILES')
        #self.uci[('FILES','na',0)].set_value(index,'FILENAME',filename)
    
    def get_metzones(self):
        '''
        Only keeps reaches that are recieving meteorlogical inputs.
        
        '''
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
        files = self.table('FILES')
        filepaths = files.loc[(files['FILENAME'].str.endswith(file_extension.lower())) |  (files['FILENAME'].str.endswith(file_extension.upper())),'FILENAME'].to_list()
        filepaths = [self.filepath.parent.joinpath(filepath) for filepath in filepaths]
        return filepaths
    
    def get_dsns(self,operation,opnid,smemn):
        dsns = self.table('EXT SOURCES')
        assert (smemn in dsns['SMEMN'].unique())
        dsns = dsns.loc[(dsns['TVOL'] == operation) & (dsns['TOPFST'] == opnid) & (dsns['SMEMN'] == smemn)]
        files = self.table('FILES').set_index('FTYPE')
        dsns.loc[:,'FILENAME'] = files.loc[dsns['SVOL'],'FILENAME'].values
        dsns = dsns[['FILENAME','SVOLNO','SMEMN','TOPFST','TVOL']]
        return dsns
    
        
    def initialize(self,name = None, default_output = 4,n=None,reach_ids = None, constituents = None):
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
        if constituents is None:
            constituents = ['Q','WT','TSS','N','TKN','OP','BOD']
        setup_binaryinfo(self,default_output = default_output,reach_ids = reach_ids,constituents=constituents)
        setup_geninfo(self)

    
    def build_targets(self):
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


#TODO: More conveince methods that should probably be in a separate module

def run_model(uci_file, wait_for_completion=True):
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

def get_filepaths(uci,file_extension):
    files = uci.table('FILES')
    filepaths = files.loc[(files['FILENAME'].str.endswith(file_extension.lower())) |  (files['FILENAME'].str.endswith(file_extension.upper())),'FILENAME'].to_list()
    filepaths = [uci.filepath.parent.joinpath(filepath) for filepath in filepaths]
    return filepaths



def setup_files(uci,name,n = 5):
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




def setup_binaryinfo(uci,default_output = 4,reach_ids = None,constituents = None):

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




def chuck(adjustment,table):
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




# Expanding opnid-opnid in tables
def format_opnids(table,valid_opnids):
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

def expand_extsources(data,valid_opnids):
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


def insert_rows(insertion_point,a,b,drop = True,reset_index = True):    
    if drop: a = a.drop(insertion_point)
    df = pd.concat([a.loc[:insertion_point], b, a.loc[insertion_point:]])
    if reset_index: df = df.reset_index(drop=True)
    return df
    



def keep_valid_opnids(table,opnid_column,valid_opnids):
    table = table.reset_index(drop = True)
    valid_indexes = [table.index[(table[opnid_column].isin(valid_opnids[operation])) & (table['TVOL'] == operation)] for operation in valid_opnids.keys()]
    valid_indexes.append(table.index[table['comments'] != ''])
    table = pd.concat([table.loc[valid_index] for valid_index in valid_indexes])
    table = table.sort_index().reset_index(drop=True)
    return table


def  RUN_comments(lines):
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

# Functions for converting the uci text file into a dictionary structure made up of my custom Table class
def reader(filepath):
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
                                              
def decompose_perlands(metzones,landcovers):
    perlands = {}
    for metzone in metzones:
        metzone = int(metzone)
        for landcover in landcovers:
            landcover = int(landcover)
            perlands[metzone+landcover] = (metzone,landcover)
    return perlands

def split_number(s):
     head = s.rstrip('0123456789')
     tail = s[len(head):]
     return head.strip(), tail

#TODO merge the get_blocks and build_uci into a single function to reduce number of for loops
def get_blocks(lines):
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

