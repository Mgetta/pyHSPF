from pathlib import Path
import os.path
import subprocess
from hspf.model.uci import UCI
from hspf.model import hbn
from hspf.reports import ReportsAccessor
from hspf.model.wdm import wdmInterface
from hspf.model import wdmReader
from hspf.outputs import outputWriter
from hspf.model import runner

class hspfModel():
    winHSPF = str(Path(__file__).resolve().parent) + '\\bin\\WinHSPFLt\\WinHspfLt.exe'


    # Imposed structures of an hspf model:
        # 1. all model files are located in the same directory as the uci file.
    def __init__(self,uci_file:str,run_model:bool = False):
                      #wdm_files:list = None,
                      #hbn_files:str = None):
        # Inputs
        self.uci = UCI(uci_file)
        self.hbn_paths= []
        self.wdm_paths = []
        self.uci_file = Path(uci_file).resolve()
        # Validate and load binary data
        self.validate_uci(run_model = run_model)
        
        
        self.hbns = hbn.hbnInterface(self.hbn_paths)
        try:
            self.wdms = wdmInterface(self.wdm_paths)
        except:
            self.wdms = None
        
        # Compositions
        self.reports = ReportsAccessor(self.uci,self.hbns,self.wdms)
        self.outputs = outputWriter(self.uci,self.hbns)

        
    def _reinitialize(self,uci_file:str,run_model:bool = False):
        self.uci = UCI(uci_file)
        self.hbn_paths= []
        self.wdm_paths = []
        self.uci_file = Path(uci_file).resolve()
        self.validate_uci(run_model = run_model)

        self.hbns = hbn.hbnInterface(self.hbn_paths)
        try:
            self.wdms = wdmInterface(self.wdm_paths)
        except:
            self.wdms = None
        self.reports = ReportsAccessor(self.uci,self.hbns,self.wdms)
        self.outputs = outputWriter(self.uci,self.hbns)

    def validate_wdms(self):
        # Ensure wdm files exist and the folders for the other file types exist relative
        # to the uci path   

        for index, row in self.uci.table('FILES',drop_comments = False).iterrows():
            file_path = self.uci_file.parent.joinpath(Path(row['FILENAME']))            
            if file_path.suffix.lower() == '.wdm':
                assert file_path.exists(),'File Specified in the UCI does not exist:' + file_path.as_posix()
                self.wdm_paths.append(file_path)
  
    def validate_pltgens(self):
        raise NotImplementedError() 

    def validate_folders(self):
        for index, row in self.uci.table('FILES',drop_comments = False).iterrows():
            file_path = self.uci_file.parent.joinpath(Path(row['FILENAME']))            
            assert file_path.parent.exists(),'File folder Specified in the UCI does not exist: ' + file_path.as_posix()


 
    def validate_uci(self,run_model:bool = False):
        # Ensure wdm files exist and the folders for the other file types exist relative
        # to the uci path   

        for index, row in self.uci.table('FILES',drop_comments = False).iterrows():
            file_path = self.uci_file.parent.joinpath(Path(row['FILENAME']))            
            if file_path.suffix.lower() == '.wdm':
                assert file_path.exists(),'File Specified in the UCI does not exist:' + file_path.as_posix()
                self.wdm_paths.append(file_path)
            elif file_path.suffix.lower() == '.hbn':
                assert file_path.parent.exists(),'File folder Specified in the UCI does not exist: ' + file_path.as_posix()
                self.hbn_paths.append(file_path)
            else:
                assert file_path.parent.exists(),'File folder Specified in the UCI does not exist: ' + file_path.as_posix()

        if (all(file_path.exists() for file_path in self.hbn_paths)) & (run_model == False):
            pass
        else:
            self.run_model()

    def run_model(self,new_uci_file = None, wait_for_completion=True):
        
        if new_uci_file is None:
            new_uci_file = self.uci_file
        runner.run_model(new_uci_file, 
                         wait_for_completion = wait_for_completion)
        
        self._reinitialize(new_uci_file,
                           run_model = False)

    def load_hbn(self,hbn_name):
        self.hbns[hbn_name] = hbn.hbnClass(self.uci_file.parent.joinpath(hbn_name).as_posix())

    def load_uci(self,uci_file,run_model:bool = False):
        self.uci = UCI(uci_file)
        self.validate_uci(run_model = run_model)
    
    def convert_wdms(self):
        for wdm_file in self.wdm_paths:
            wdmReader.readWDM(wdm_file,
                              wdm_file.parent.joinpath(wdm_file.name.replace('.wdm','.hdf5').replace('.WDM','hdf5')))
        self._load_wdms()
    
    def load_wdm(self,wdm_file):
        raise NotImplementedError()

    def _load_wdms(self):
        self.wdms = wdmInterface(self.wdm_paths)
           

    # Model checks         
    def check_filename_exist(self,file_extension: str):
        table = self.uci.table('FILES',drop_comments = False)
        uci_path = Path(self.uci_file).parent
        check = []
        for index, row in table.iterrows():
            file_path = Path(row['FILENAME'])
            if file_path.suffix == file_extension:
                relative_path = (uci_path / file_path).resolve()
                check.append(relative_path.exists())        
        return all(check)
            
        
        
        
    def check_filename_match(self,file_names):
        table = self.uci.table('FILES',drop_comments = False)
        #uci_path = Path(mod.uci.filepath).parent
        for index, row in table.iterrows():
            file_path = Path(row['FILENAME'])
            if file_path.suffix == '.wdm':
                assert(file_path.name in [file_name.name for file_name in file_names])
    
    def get_filename_paths(self,file_extension):
        table = self.uci.table('FILES',drop_comments = False)
        wdm_files = []
        for index, row in table.iterrows():
            file_path = Path(row['FILENAME'])
            if file_path.suffix == file_extension:
                wdm_files.append(self.uci_file.parent.joinpath(Path(file_path)))
        return wdm_files    
    
    def update_filename_paths(self,file_names):
        table = self.uci.table('FILES',drop_comments = False)
        for index, row in table.iterrows():
            file_path = Path(row['FILENAME'])
            for file_name in file_names:
                if file_name.name == file_path.name:  
                    #print(Path(os.path.relpath(wdm_file, start = uci_path)).as_posix())
                    table.loc[index,'FILENAME'] = Path(os.path.relpath(file_name, start = self.uci_file.parent)).as_posix()
        self.uci.replace_table(table,'FILES')
    
    def check_filename_folder(self,file_extension):
        table = self.uci.table('FILES',drop_comments = False)
        for index, row in table.iterrows():
            file_path = Path(row['FILENAME'])
            if file_path.suffix == file_extension:  
                if self.model_path.joinpath(file_path.parent).exists():
                    continue
                else:
                    table.loc[index,'FILENAME'] = Path(os.path.relpath(file_path.name, start = self.uci_file.parent)).as_posix()
        self.uci.replace_table(table,'FILES')

