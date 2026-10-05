import numpy as np
import pandas as pd


#TODO: Views based only on the tables not the uci document class
def simulated_opnids(uci):
    opnseq = uci.table('OPN SEQUENCE')
    return  {'PERLND': opnseq['SEGMENT'][opnseq['OPERATION'] == 'PERLND'].astype(int).to_list(),
            'RCHRES': opnseq['SEGMENT'][opnseq['OPERATION'] == 'RCHRES'].astype(int).to_list(),
            'IMPLND': opnseq['SEGMENT'][opnseq['OPERATION'] == 'IMPLND'].astype(int).to_list(),
            'GENER' : opnseq['SEGMENT'][opnseq['OPERATION'] == 'GENER'].astype(int).to_list(),
            'COPY'  : opnseq['SEGMENT'][opnseq['OPERATION'] == 'COPY'].astype(int).to_list()}

def infer_metzones(uci):
    """Infer meteorological zone assignments from the EXT SOURCES table.

    For each operation (PERLND, IMPLND, RCHRES), identifies which
    operation IDs receive PREC (precipitation) input, maps them to met
    zones based on the ``SVOLNO`` column of EXT SOURCES, and merges with
    GEN-INFO to attach land-cover (LSID) or reach (RCHID/LKFG) metadata.

    Returns
    -------
    dict
        Mapping of operation name (``'PERLND'``, ``'IMPLND'``,
        ``'RCHRES'``) to a :class:`pandas.DataFrame` containing at
        minimum the columns ``metzone`` and ``SVOLNO``.  PERLND and
        IMPLND DataFrames additionally contain ``LSID`` and ``landcover``
        columns; RCHRES DataFrames contain ``RCHID`` and ``LKFG``.
    """
    operations = ['PERLND','IMPLND','RCHRES']
    dic = {}
    
    extsrc = uci.table('EXT SOURCES')
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
        geninfo = uci.table(operation,'GEN-INFO')
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
def get_filepaths(uci,file_extension):
    """Return file paths from the FILES table matching the given extension.

    Parameters
    ----------
    file_extension : str
        File extension to filter by, including the leading dot
        (e.g. ``'.wdm'``).  The comparison is case-insensitive.

    Returns
    -------
    list of pathlib.Path
        Absolute paths constructed by joining each matching filename with
        the directory that contains the UCI file.
    """
    files = uci.table('FILES')
    filepaths = files.loc[(files['FILENAME'].str.endswith(file_extension.lower())) |  (files['FILENAME'].str.endswith(file_extension.upper())),'FILENAME'].to_list()
    filepaths = [uci.filepath.parent.joinpath(filepath) for filepath in filepaths]
    return filepaths

def get_dsns(uci,operation,opnid,smemn):
    """Return dataset numbers (DSNs) for a given operation, OPNID, and member name.

    Looks up matching rows in the EXT SOURCES table, then joins with the
    FILES table to attach the source filename to each DSN record.

    Parameters
    ----------
    operation : str
        Target volume operation name (``TVOL``), e.g. ``'RCHRES'``.
    opnid : int
        Target operation ID (``TOPFST``) to filter on.
    smemn : str
        Source member name (e.g. ``'PREC'``, ``'EVAP'``).  Must be
        present in the ``SMEMN`` column of EXT SOURCES.

    Returns
    -------
    pandas.DataFrame
        Filtered EXT SOURCES rows with columns ``FILENAME``, ``SVOLNO``,
        ``SMEMN``, ``TOPFST``, and ``TVOL``.
    """
    dsns = uci.table('EXT SOURCES')
    assert (smemn in dsns['SMEMN'].unique())
    dsns = dsns.loc[(dsns['TVOL'] == operation) & (dsns['TOPFST'] == opnid) & (dsns['SMEMN'] == smemn)]
    files = uci.table('FILES').set_index('FTYPE')
    dsns.loc[:,'FILENAME'] = files.loc[dsns['SVOL'],'FILENAME'].values
    dsns = dsns[['FILENAME','SVOLNO','SMEMN','TOPFST','TVOL']]
    return dsns



def targets(uci):
    """Build a calibration target table from PERLND land covers.

    Uses ``self.opnid_dict['PERLND']`` together with the SCHEMATIC table
    to compute the total contributing area for each unique land-cover
    type.  The result is a summary DataFrame suitable for calibration
    target specification.

    Returns
    -------
    pandas.DataFrame
        One row per unique land-cover type with columns:

        * ``uci_name`` – LSID string from GEN-INFO.
        * ``lc_number`` – integer land-cover index.
        * ``area`` – total area (sum of AFACTR values from SCHEMATIC).
        * ``npsl_name`` – empty string placeholder for an external name.
        * ``TSS``, ``N``, ``TKN``, ``OP``, ``BOD`` – empty string
            placeholders for constituent calibration targets.
        * ``dom_lc`` – ``1`` for the land cover with the largest area,
            ``pd.NA`` for all others.
    """  
    geninfo = uci.table('PERLND','GEN-INFO')  
    targets = uci.opnid_dict['PERLND'].loc[:,['LSID','landcover']] #.drop_duplicates(subset = 'landcover').loc[:,['LSID','landcover']].reset_index(drop = True)
    targets.columns = ['LSID','lc_number']
    schematic = uci.table('SCHEMATIC')
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



def masslinks(uci):
    dfs = []
    for table_name in uci.table_names('MASS-LINK'):
        mlno = table_name.split('MASS-LINK')[1]
        masslink = uci.table('MASS-LINK', table_name)
        masslink.insert(0, 'MLNO', mlno)
        dfs.append(masslink)
    _masslinks = pd.concat(dfs, ignore_index=True)
    return _masslinks