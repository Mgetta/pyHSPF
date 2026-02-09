

'''
An outlet defined by a list of reach ids
    Hourly constituent concentration output
        Q,TSS,TP,OP,TKN,N,DO,BOD,CHLA
Monthly watershed loading rates
    Q,TSS,TP,OP,TKN,N,DO,BOD,CHLA
Monthly RCHRES constituent outflows
    Q,TSS,TP,OP,TKN,N,DO,BOD,CHLA
Monthly RCHRES constituent inflows
    Q,TSS,TP,OP,TKN,N,DO,BOD,CHLA
Monthly weighted catchment constituent loading rate (from reports)
    Q,TSS,TP,OP,TKN,N
Monthly weighted catchment surface runoff (from reports)
Monthly PERLND/IMPLND constituent loading rate
    Q,TSS,TP,OP,TKN,N,BOD
Monthly PRELND/IMPLNDsurface runoff 
'''

#%% outlet
import pandas as pd
from hspf import reports

class outputWriter:
        def __init__(self,uci,hbn,output_folder = None,constituents = None,model_name = None):
            self.uci = uci
            self.hbn = hbn
            
            if constituents is None:
                constituents = ['Q','TSS','TP','TKN','N','OP']
            self.constituents = constituents
            
            if output_folder is None:
                self.output_folder = self.uci.filepath.parent

            if model_name is None:
                self.model_name = self.uci.filepath.stem
        
        def set_output_folder(self,output_folder):
            self.output_folder = output_folder
        
        def set_constituents(self,constituents):
            self.constituents = constituents

        def write_outlet_output(self,name,reach_ids,time_step=4):
            filepath = self.output_folder.joinpath(name + '_outlet_output.csv')
            get_outlet_output(self.hbn,name, reach_ids,self.output_folder, self.constituents,time_step).to_csv(filepath,index = False)
            return filepath                                                                                            

        def write_watershed_output(self,name, reach_ids,time_step=4):
            filepath = self.output_folder.joinpath(name + '_annual_watershed_loading.csv')
            get_watershed_output(self.uci,self.hbn,name, reach_ids,self.output_folder, self.constituents,time_step).to_csv(filepath,index = False)
            return filepath
                                                                                                       

        def write_reach_output(mod,reach_ids,output_folder = None,constituents = None,time_step='D'):
            raise NotImplementedError

        def write_catchment_loading_output(self):
            filepath = self.output_folder.joinpath('annual_catchment_loading.csv')
            get_catchment_output(self.uci,self.hbn,self.output_folder,self.constituents).to_csv(filepath,index = False)
            return filepath

        def write_catchment_runoff_output(mod,reach_ids,output_folder = None,constituents = None,time_step='D'):
            raise NotImplementedError

        def write_landcover_loading_output(mod,reach_ids,output_folder = None,constituents = None,time_step='D'):
            raise NotImplementedError

        def write_landcover_runoff_output(mod,reach_ids,output_folder = None,constituents = None,time_step='ME'):
            raise NotImplementedError

def get_outlet_output(hbn,name, reach_ids,output_folder = None, constituents = None,time_step='D'):
    if constituents is None:
        constituents = ['Q','TSS','TP','TKN','N','OP']

    dfs = []
    for constituent in constituents:
        df_temp = hbn.get_reach_constituent(constituent,reach_ids,time_step)
        df_temp.reset_index(inplace = True)
        df_temp.columns = ['datetime','value'] # Dangerous. Will break if the hbn structure changes
        df_temp['constituent'] = constituent
        df_temp['name'] = name
        dfs.append(df_temp)

    df = pd.concat(dfs)
    return df


def get_watershed_output(uci,hbn,name, reach_ids,output_folder = None, constituents = None,time_step='D'):
    if constituents is None:
        constituents = ['Q','TSS','TP','TKN','N','OP']

    df = pd.concat([reports.average_annual_watershed_loading(uci,hbn,constituent,reach_ids) for constituent in constituents])
    return df

def get_catchment_output(uci,hbn,output_folder = None, constituents = None):
    if constituents is None:
        constituents = ['Q','TSS','TP','TKN','N','OP']

    df = pd.concat([reports.average_annual_catchment_loading(uci,hbn,constituent) for constituent in constituents])
    return df

