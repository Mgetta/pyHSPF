
from pathlib import Path
import subprocess
import sys
import concurrent.futures



winHSPF = str(Path(__file__).resolve().parent) + '\\bin\\WinHSPFLt\\WinHspfLt.exe'

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




def run_uci(uci_file:str, ):
    """
    convenience function to run a single model uci file.
    """
    print(f"Starting model: {uci_file}")
    subprocess.run([winHSPF, uci_file]) 
    print(f"Completed model: {uci_file}")


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
 