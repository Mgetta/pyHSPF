# -*- coding: utf-8 -*-
"""
Created on Thu Oct 13 09:26:05 2022

@author: mfratki
"""
from pathlib import Path
import csv
from datetime import datetime
import os.path
import shutil
import subprocess
import concurrent.futures
from hspf.uci import UCI
from hspf import hbn
from hspf.reports import ReportsAccessor
from hspf.wdm import wdmInterface
from hspf import wdmReader
from hspf.outputs import outputWriter
 


winHSPF = str(Path(__file__).resolve().parent) + '\\bin\\WinHSPFLt\\WinHspfLt.exe'


# Only for accessing information regarding a specific uci_file
# Trying to segregate manipulating the uci file and information about the uci file


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

    def run_model(self,new_uci_file = None,):
        
        if new_uci_file is None:
            new_uci_file = self.uci_file
        
        # new_uci_file = self.model_path.joinpath(uci_name)
        # self.uci.write(new_uci_file)

        subprocess.run([winHSPF,Path(new_uci_file).resolve().as_posix()]) #, stdout=subprocess.PIPE, creationflags=0x08000000)
        self._reinitialize(new_uci_file,run_model = False)

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



def run_uci(uci_file: str, cwd=None):
    """Run one UCI with model output files rooted in *cwd*."""
    uci_file = Path(uci_file).resolve()
    if cwd is None:
        cwd = uci_file.parent
    print(f"Starting model: {uci_file}")
    completed = subprocess.run([winHSPF, uci_file.as_posix()], cwd=Path(cwd))
    print(f"Completed model: {uci_file}")
    return completed


def check_run_status(uci_file):
    """Return completion and error information from a UCI run."""
    uci_file = Path(uci_file).resolve()
    model = UCI(uci_file, infer_metzones=False)
    files = model.table('FILES', drop_comments=False)
    messages = files.loc[files['FTYPE'].str.strip() == 'MESSU', 'FILENAME']
    ech_path = uci_file.parent / (messages.iloc[0].strip() if len(messages) else f'{uci_file.stem}.ech')
    log_path = uci_file.parent / f'{uci_file.stem}.log'
    lines = ech_path.read_text(errors='replace').splitlines() if ech_path.exists() else []
    ignored = ('ERROR/WARNING', 'CONTINUITY ERROR REPORTED',
               'RELERR IS THE RELATIVE ERROR',
               'ERROR IS (STOR-STORS) - MATDIF')
    errors = [line.strip() for line in lines
              if 'ERROR' in line.upper() and
              not any(text in ' '.join(line.upper().split()) for text in ignored)]
    end_of_job = any('END OF JOB' in line.upper() for line in lines[-100:])
    return {
        'ok': end_of_job and not errors,
        'end_of_job': end_of_job,
        'n_errors': len(errors),
        'errors': errors,
        'ech_path': ech_path,
        'log_path': log_path,
    }


def _run_staged_uci(uci_file, run_root, stage_files):
    started = datetime.now()
    uci_file = Path(uci_file).resolve()
    run_dir = Path(run_root).resolve() / uci_file.stem
    run_dir.mkdir(parents=True, exist_ok=True)
    run_uci_path = run_dir / uci_file.name
    shutil.copy2(uci_file, run_uci_path)
    for stage_file in stage_files:
        shutil.copy2(stage_file, run_dir / Path(stage_file).name)
    completed = run_uci(run_uci_path, cwd=run_dir)
    status = check_run_status(run_uci_path)
    status['returncode'] = getattr(completed, 'returncode', 0)
    status['ok'] = status['ok'] and status['returncode'] == 0
    status['started'] = started
    status['ended'] = datetime.now()
    status['run_dir'] = run_dir
    return run_uci_path, status


def _append_run_log(log_csv, uci_path, status, run_dir_kept):
    if log_csv is None:
        return
    log_csv = Path(log_csv)
    log_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = ['scenario', 'start', 'end', 'minutes', 'ok', 'n_errors',
              'run_dir_kept']
    row = {
        'scenario': Path(uci_path).stem,
        'start': status['started'].isoformat(timespec='seconds'),
        'end': status['ended'].isoformat(timespec='seconds'),
        'minutes': (status['ended'] - status['started']).total_seconds() / 60,
        'ok': status['ok'],
        'n_errors': status['n_errors'],
        'run_dir_kept': run_dir_kept,
    }
    write_header = not log_csv.exists() or log_csv.stat().st_size == 0
    with log_csv.open('a', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def run_batch_staged(uci_files, run_root, stage_files, batch_size=4,
                     on_complete=None, cleanup=True, skip_if=None,
                     log_csv=None):
    """Stage and run UCIs through a rolling, disk-bounded thread pool."""
    if batch_size < 1:
        raise ValueError('batch_size must be at least 1')
    uci_files = [Path(path).resolve() for path in uci_files]
    stage_files = [Path(path).resolve() for path in stage_files]
    selected = [path for path in uci_files if skip_if is None or not skip_if(path)]
    results = []
    iterator = iter(selected)
    with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
        pending = {}
        for uci_file in iterator:
            future = executor.submit(_run_staged_uci, uci_file, run_root, stage_files)
            pending[future] = uci_file
            if len(pending) == batch_size:
                break
        while pending:
            done, _ = concurrent.futures.wait(
                pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                source_uci = pending.pop(future)
                try:
                    run_uci_path, status = future.result()
                except Exception as exc:
                    run_dir = Path(run_root).resolve() / source_uci.stem
                    now = datetime.now()
                    status = {
                        'ok': False, 'end_of_job': False, 'n_errors': 1,
                        'errors': [str(exc)], 'ech_path': None, 'log_path': None,
                        'started': now, 'ended': now, 'run_dir': run_dir,
                    }
                    run_uci_path = run_dir / source_uci.name
                result = None
                callback_ok = True
                if on_complete is not None:
                    try:
                        result = on_complete(run_uci_path, status)
                    except Exception as exc:
                        callback_ok = False
                        status['callback_error'] = str(exc)
                        print(f"Completion callback failed for {source_uci}: {exc}")
                remove_run_dir = cleanup and status['ok'] and callback_ok
                if remove_run_dir:
                    shutil.rmtree(status['run_dir'])
                _append_run_log(log_csv, source_uci, status, not remove_run_dir)
                results.append((source_uci, status, result))
                try:
                    next_uci = next(iterator)
                except StopIteration:
                    continue
                next_future = executor.submit(
                    _run_staged_uci, next_uci, run_root, stage_files)
                pending[next_future] = next_uci
    return results


def run_batch_files(file_list, max_concurrent=4):
    """
    Takes a list of .uci file paths and runs them N at a time.
    """
    # Create a pool of workers (threads)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        # Submit all jobs to the pool
        future_to_file = {
            executor.submit(run_uci, uci_file): uci_file 
            for uci_file in file_list
        }
        
        # Monitor completion (optional, but good for error catching)
        for future in concurrent.futures.as_completed(future_to_file):
            uci_file = future_to_file[future]
            try:
                future.result() # This will raise exceptions if run_uci failed
            except Exception as exc:
                print(f"File {uci_file} generated an exception: {exc}")
                

# class runManager():
#     def __init__()
    
#     self.requests = {'original': 0,'copy0':0,'copy1':0,'copy2':0}
#     self.childs = {'original':None,
#                 'copy0':None,
#                 'copy1':None,
#                 'copy2':None}
    
#     def original_run(self):
#         table = self.table('FILES',drop_comments = False)
#         # Assumes duplicate uci are in uci/copy/
#         wdm_files = [ (index,name.split('/')[-1]) for index,name in enumerate(table['FILENAME'])
#                  if name.split('.')[-1] in ['ech','out','wdm']]
#         for file in wdm_files:
#             table.iloc[file[0], table.columns.get_loc('FILENAME')] = '../wdms/' + file[1]
    
#         hbn_files =  [ (index,name.split('/')[-1]) for index,name in enumerate(table['FILENAME'])
#                  if name.split('.')[-1] in ['hbn']]
#         for file in hbn_files:
#             table.iloc[file[0], table.columns.get_loc('FILENAME')] = '../hbns/' + file[1]
        
#         self.uci['FILES']['na']['table'][0] = table
#         self.update_lines('FILES')
        
#     def duplicate_run(self,copy): #copy1,copy2,copy3 ... copy7 only options
#         table = self.table('FILES',drop_comments = False)
        
#         # Assumes duplicate uci are in uci/copy/
#         wdm_files = [ (index,name.split('/')[-1]) for index,name in enumerate(table['FILENAME'])
#                  if name.split('.')[-1] in ['ech','out','wdm']]
#         for file in wdm_files:
#             table.iloc[file[0], table.columns.get_loc('FILENAME')] = '../../wdms/' + copy + '/' + file[1]
    
#         hbn_files =  [ (index,name.split('/')[-1]) for index,name in enumerate(table['FILENAME'])
#                  if name.split('.')[-1] in ['hbn']]
#         for file in hbn_files:
#             table.iloc[file[0], table.columns.get_loc('FILENAME')] = '../../hbns/' + file[1]
         
#         self.uci['FILES']['na']['table'][0] = table
#         self.update_lines('FILES')