    

from hspf.core.types import OutputLevel


DEFAULT_OUTPUT = OutputLevel.MONTHLY
N_HBNS = 5
DEFUALT_CONSTITUENTS = ['Q','WT','TSS','N','TKN','OP','BOD']


def initialize(self,name = None, default_output = DEFAULT_OUTPUT,n=None,reach_ids = None, constituents = None):
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
        constituents = DEFUALT_CONSTITUENTS

    if n is None and reach_ids is not None:
        n = int(len(reach_ids)/2)
    else:
        n = N_HBNS

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
    QUALID_MAP = {
        "NH3+NH4": "NH3+NH4",
        "NO2+NO3": "NO3",
        "TAM": "NH3+NH4",
        "FLUORIDE": "FLOURIDE",
        "ORG": "BOD",
        "F.COLIFORM": "F.COLIFORM",
        "F.Coliform": "F.COLIFORM",
        "NH3": "NH3+NH4",
        "OrgM": "BOD",
        "Total Ph": "TP",
        "PO4": "ORTHO P",
        "NO2 NO3": "NO3",
        "NO3+NO2": "NO3",
        "BOD": "BOD",
        "Nitrate": "NO3",
        "ORTHO P": "ORTHO P",
        "NO3": "NO3",
        "Total Phos": "TP",
        "Total Ammo": "NH3+NH4",
    }

    for key in uci.uci.keys():
        if key[1] == 'QUAL-PROPS' and key[0] in ['PERLND','IMPLND']:
            table = uci.table(key[0], key[1], key[2])
            # Important safeguards to ensure subsequent functions and modules work correctly
            # Perhaps future improvements for downstream methods could be based on qualid name instead of assuming a specific name?
            assert len(table['QUALID'].unique()) == 1, f"Multiple QUALIDs found in {uci.name}: {table['QUALID'].unique()}"
            assert(set(table['QUALID'].unique()).issubset(set(QUALID_MAP.keys()))), f"Unknown QUALID found in {uci.name}: {set(table['QUALID'].unique()) - set(QUALID_MAP.keys())}"
            qualid = table['QUALID'].iloc[0]
            uci.update_table(QUALID_MAP[qualid],key[0],'QUAL-PROPS',key[2],columns = 'QUALID',operator = 'set')

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

    table = uci.table('FILES',drop_comments = False)
    

    for index, row in table.iterrows():
        filename = Path(row['FILENAME'])
        if filename.suffix in ['.wdm','.ech','.out']:
            table.loc[index,'FILENAME'] = filename.name
        if filename.suffix in ['.hbn']:
            table.loc[index,'FILENAME'] = filename.name
        if filename.suffix in ['.plt']:
            table.drop(index,inplace = True)
            
    # Get the unit numbers used by PLTGEN PLOTFL entries
    pltgen_nums = []
    if 'PLTGEN' in uci.block_names():
        pltgen_nums = uci.table('PLTGEN','PLOTINFO')['PLOTFL'].tolist()

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

