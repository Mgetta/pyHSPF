from pathlib import Path

from hspf import uci

uci = uci.UCI(Path(__file__).parent / 'data' / 'Clearwater.uci')



uci.add_parameter_template('PERLND','PWAT-PARM2',0,'LZSN')

