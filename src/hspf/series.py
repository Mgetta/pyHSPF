'''
General API for accessing reporting constituents and time series output from the HSPF model.

1. Raw timeseries directly from the hbn
2. 
3. Reporting constituents composed of 1 or more raw timeseries
    'Total Phosphorus', 
    'Total Nitrogen',
    'Sediment',
    'Orthophosphate',
    'Nitrate Nitrite',
    'Ammonia',
    'Total Kjeldahl Nitrogen',
    'Biochemical Oxygen Demand',
    'Dissolved Oxygen',
    'Chlorophyll a',
    'Water Temperature',
    'Water',
    # constituents that are derived from the member transform
    'dissolved_orthophosphate',
    'particulate_orthophosphate_sand',
    'particulate_orthophosphate_silt',
    'particulate_orthophosphate_clay',
    'particulate_orthophosphate',
    'organic_refactory_phosphorous',
    'organic_refactory_carbon',
    'labile_oxygen_demand_phosphorous',
    'dissolved_total_ammonia',
    'dissolved_nitrate',
    'organic_refactory_nitrogen',
    'labile_oxygen_demand_nitrogen'


1. Outputs from Land Areas
2. Outputs from Reaches
3. Inflows into Reaches
    - Target timeseries metadata
    - Source timeseries metadata

'''

#%%

import math
from duckdb import operator
import pandas as pd
from dataclasses import dataclass, replace
from typing import NamedTuple

from tables import table
from hspf.core import registries
from hspf.core.constituents import ReportingConstituent, Form, FORM_SEMANTICS
from hspf.core.types import OperationKey, OutputLevel, OperationType, Activity, TIMESTEP_LABELS, PANDAS_FREQ
from hspf.core.units import Unit, affine_unit_transform, OUTPUT_BASIS, UnitSpec, seconds_in_interval, DimensionConversionError, convert
from hspf.core import constituents
from hspf.core.registries import  CATALOG_REGISTRY, get_constituent_spec, query_boundary_table,get_source_unit_spec
#%%
# None of this should live here...
CF2CFS = {'hourly':3600,
          'daily':86400,
          'monthly':2592000,
          'yearly':31536000,
          'h':3600,
          'D':86400,
          'ME':2592000,
          'Y':31536000,
          'YE':31536000,
          2:3600,
          3:86400,
          4:2592000,
          5:31536000}

# Default aggregation method for each unit (mean or sum).
AGG_DEFAULTS = {'cfs':'mean',
                'mg/l':'mean',
                'degF': 'mean',
                'lb':'sum'}

# Default display unit for each constituent abbreviation.
UNIT_DEFAULTS = {'Q': 'cfs',
                 'TSS': 'mg/l',
                 'TP' : 'mg/l',
                 'OP' : 'mg/l',
                 'TKN': 'mg/l',
                 'N'  : 'mg/l',
                 'WT' : 'degF',
                 'WL' : 'ft'}

NET_VOLUME_FLOOR = 1e-6

@dataclass
class Query:
    operation: OperationKey
    reach_id: int
    constituent: ReportingConstituent
    form: Form
    output_level: OutputLevel
    sign: int
    upstream_reach_ids: list[int] | None = None
    by: str | None = None

#TODO: implement a dataclass for better scale provenance
# @dataclass(frozen=True)
# class PlanRow:
#     operation: OperationType
#     opnid: int
#     activity: Activity
#     variable: str
#     unit_spec: UnitSpec              # Native HBN unit (or inflow door unit)
#     sign: float = 1.0                # +1.0 or -1.0 (reach subtraction)
#     coefficient: float = 1.0         # Registry stoichiometric coefficient (e.g., BOD -> P)
#     afactr: float = 1.0              # Schematic area factor (acres)
#     mfactor: float = 1.0             # Mass-link / network transfer factor
#     unit_factor: float = 1.0         # Unit conversion factor to target_measure
#     offset: float = 0.0
#     group_by: str | int | None = None

#     @property
#     def scale(self) -> float:
#         return self.sign * self.coefficient * self.afactr * self.mfactor * self.unit_factor

class PlanRow(NamedTuple):
    operation: str        # "RCHRES"
    opnid: int
    activity: str
    variable: str
    unit_spec: UnitSpec
    scale: float = 1   # sign × term coeff (× AFACTR × MFACTOR in the land doors)
    offset: float = 0
    group_by: str | int | None = None

@dataclass(frozen=True)
class FetchPlan:
    numerator: tuple[PlanRow, ...]
    denominator: tuple[PlanRow, ...] | None   # None ⇒ extensive request
    target_unit: str
    tcode: int
    operator: str

#TODO: Add support for specifying target_unit explicitly in reach_series function.
def reach_series(store,reach_ids, constituent, form, period = 'monthly',units = None, metadata = False, *,
                 carrier = None, binding = None, substance = None):
    '''
    
    
    - Retrieve the time series for the specified reach IDs, constituent, and form. For a reach this typically maps 1:1 to a (smemn, ssub1, ssub2) combination in the HSPF model.
    - Can also pass any standard hspf binary name
    '''

    

    output_level = TIMESTEP_LABELS[period]
    pairs = tuple((abs(i), math.copysign(1.0, i)) for i in reach_ids)
    constituent = ReportingConstituent(constituent)
    form = Form(form)
    cspec = get_constituent_spec(constituent, form)

    if units is not None:
        #TODO: Validate that target_unit has the necessary measure and normalization for the constituent forms.
        target_unit = registries.get_unit_spec(units)
    else:
        target_unit = cspec.target_unit


    nf = cspec.numerator_form
    num_plan = _resolve_reach(constituent, nf, pairs, target_unit.measure)
    den_plan = None

    if cspec.denominator_constituent != 'NULL': #TODO: use types instead
        df = cspec.denominator_form
        den_plan = _resolve_reach(ReportingConstituent(cspec.denominator_constituent), df, pairs, target_unit.normalization)

        
    

    plan = FetchPlan(
        numerator=num_plan,
        denominator=den_plan,
        tcode=output_level,
        operator='sum',
        target_unit=target_unit)

    num = _evaluate(
        store,
        plan.numerator,
        target_measure=plan.target_unit.measure,
        tcode=plan.tcode,
        operator=plan.operator,
    )

    if plan.denominator is not None:
        den = _evaluate(
            store,
            plan.denominator,
            target_measure=plan.target_unit.normalization,
            tcode=plan.tcode,
            operator=plan.operator,
        )
        out = num / den.where(den > NET_VOLUME_FLOOR)
    else:
        out =  num


    if target_unit.interval is not None:
        if target_unit.interval != 'ivld':
            #TODO: How to handle for non extensive forms?
            out = out / out.index.map(lambda x: seconds_in_interval(x, output_level))

    out = out + target_unit.offset
    if metadata:
        return out, plan

    
    return out #TODO: not have two different return states...


def land_series():
    raise NotImplementedError("land_series function is not yet implemented.")


def reach_inflows(store, uci, reach_ids, constituent, form, period='monthly', by=None, pathways=None):

    raise NotImplementedError("reach_inflows function is not yet implemented.")


def catchment_series(uci,store,reach_ids, constituent, form, period = 'monthly', units=None, metadata=False, *,
                     carrier = None, binding = None, substance = None, pathway = None,
                     process = None, source = None, landcover = None, by = None):
    '''
    1. Direct output from PERLNDS/IMPLNDS in catchment
    2. constituent loading to the reach
    
    '''

    if isinstance(reach_ids, int):
        reach_ids = [reach_ids]
    

    output_level = TIMESTEP_LABELS[period]
    constituent = ReportingConstituent(constituent)
    form = Form(form)
    cspec = get_constituent_spec(constituent, form)

    if units is not None:
        #TODO: Validate that target_unit has the necessary measure and normalization for the constituent forms.
        target_unit = registries.get_unit_spec(units)
        cspec = replace(cspec, target_unit=target_unit)

    nf = cspec.numerator_form
    numerator_unit = cspec.target_unit.measure
    num_plan = _resolve_catchment(uci,constituent, nf, reach_ids, numerator_unit)
    den_plan = None

    if cspec.denominator_constituent != 'NULL': #TODO: use types instead
        df = cspec.denominator_form
        denominator_unit = cspec.target_unit.normalization #registries.get_constituent_spec(cspec.denominator_constituent, df).target_unit
        denominator_constituent = ReportingConstituent(cspec.denominator_constituent)
        den_plan = _resolve_catchment(uci, denominator_constituent, df, reach_ids, denominator_unit)
    


    
    plan = FetchPlan(
        numerator=num_plan,
        denominator=den_plan,
        tcode=output_level,
        operator='sum',
        target_unit=cspec.target_unit)

    num = _evaluate(
        store,
        plan.numerator,
        target_measure=plan.target_unit.measure,
        tcode=plan.tcode,
        operator=plan.operator,
    )

    if plan.denominator is not None:
        den = _evaluate(
            store,
            plan.denominator,
            target_measure=plan.target_unit.normalization,
            tcode=plan.tcode,
            operator=plan.operator,
        )
        out = num / den.where(den > NET_VOLUME_FLOOR)
    else:
        out =  num


    if cspec.target_unit.interval is not None:
        if cspec.target_unit.interval != 'ivld':
            #TODO: How to handle for non extensive forms?
            out = out / out.index.map(lambda x: seconds_in_interval(x, output_level))

    out = out + cspec.target_unit.offset
    
    if metadata:
        return out, plan

    
    return out #TODO: not have two different return states...

def watershed_series(uci, store, reach_ids, constituent, form,period="monthly", by=None, upstream_reach_ids=None, pathways=None,):
    # 1. Expand reach_ids to all contributing reaches in the subwatershed
    # #TODO: Move land_to_reach filtering into the network topology or a dedicated function

    reach_ids = set(rid for sublist in reach_ids for rid in uci.network._upstream(sublist))  # flatten the list of lists
    if upstream_reach_ids is not None:
        upstream_reach_ids = set(rid for sublist in upstream_reach_ids for rid in sublist)  # flatten the list of lists
        reach_ids -= upstream_reach_ids
    reach_ids = list(reach_ids)

    return catchment_series(
        uci, store, reach_ids, constituent, form,
        period=period, by=by, pathways=pathways,
    )


def hbn_series(store, operation, opnid, tcons, activity, tcode):

    term = CATALOG.loc[(CATALOG['operation'] == operation) &
                (CATALOG['activity'] == activity) &
                (CATALOG['hbn_name'] == tcons)]  
    
    if term.empty:           # inventory peek only (P13)
        raise ValueError(f"No matching term found in catalog for operation={operation}, activity={activity}, hbn_name={tcons}")

    store.record(operation, opnid, activity, tcode)

    raise NotImplementedError("hbn_series function is not yet implemented.")


def hbn_inventory():
    raise NotImplementedError("hbn_inventory function is not yet implemented.")

def parameters():
    raise NotImplementedError("parameters function is not yet implemented.")

def locations():
    raise NotImplementedError("locations function is not yet implemented.")


def _evaluate(store, rows: tuple[PlanRow, ...], tcode: int, target_measure: Unit | None = None, period: str = "monthly", operator: str = "sum"):
    parts = []
    for r in rows:
        s = store.record(r.operation.value, r.opnid, r.activity.value, tcode)[r.variable] * r.scale + r.offset
        parts.append(s)

    df = pd.concat(parts, axis=1)
    df = getattr(df, operator)(axis=1)

    # apply unit conversion if necessary


    return df



def _resolve_reach(constituent, form, pairs,target_unit):
    rows = []
    result = query_boundary_table('reach_outputs',constituent,form)
    for reach_id, reach_sign in pairs:
        for _, row in result.iterrows():
            unit_spec = registries.get_unit_spec(row.units_english)
            unit_factor, offset = affine_unit_transform(unit_spec.measure, target_unit)
            rows.append(PlanRow(
                    operation=OperationType(row.operation),
                    activity=Activity(row.activity),
                    opnid=reach_id,
                    variable=row.hbn_name,
                    unit_spec=unit_spec, #TODO: rename to native/target
                    scale=float(row.coefficient) * reach_sign * unit_factor,
                    offset = offset + unit_spec.offset,
                    group_by=None
                ))
    return rows    


def _query_catchment(uci,constituent, form, reach_ids):
    transfers = uci.network.topology.member_transfers
    mask = (transfers['TVOLNO'].isin(reach_ids) & 
           (transfers['TVOL'] == 'RCHRES') &
           (transfers['SVOL'].isin(['PERLND','IMPLND']))
            )
    inflows = transfers.loc[mask]
    result = registries.query_boundary_table('reach_inflows',constituent,form)
    result = result.merge(inflows, how='inner', right_on=['TMEMN','TMEMSB1','TMEMSB2'], left_on= ['name','sub1','sub2'])
    result = result.merge(registries.CATALOG_REGISTRY.catalog, how='left', 
                          left_on=['SVOL','SGRPN','SMEMN'], 
                          right_on=['operation','activity','name'],
                          suffixes=['_inflows','_sources'])
    return result

def _resolve_catchment(uci,constituent, form, reach_ids, target_unit):
    '''
    Information derived from an instance of a UCI object:
        1. hbn names associated with each member transfer
        2. bod transfer coefficients. The model derives from CONV-VAL1 in the RCHRES block but currently I just use a hardcoded value in the inflows registry table.
        3. Units of each qual is also defined in the qual-props table.
    
    Note that the effective factor includes area factor and any mfactors. 
      This means that the hbn output is always scaled to lbs/ivld. I did this as the topology member_transfers table combines network and schematic_masslink transfers where network transfers don't distinguish the AFACTR and MFACTOR.
    
    '''

    # combine registry and run specific information
    transfers = uci.network.topology.member_transfers
    mask = (transfers['TVOLNO'].isin(reach_ids) & 
           (transfers['TVOL'] == 'RCHRES') &
           (transfers['SVOL'].isin(['PERLND','IMPLND']))
            )
    inflows = transfers.loc[mask]
    result = registries.query_boundary_table('reach_inflows',constituent,form)
    result = result.merge(inflows, how='inner', right_on=['TMEMN','TMEMSB1','TMEMSB2'], left_on= ['name','sub1','sub2'])
    result = result.merge(registries.CATALOG_REGISTRY.catalog, how='left', 
                          left_on=['SVOL','SGRPN','SMEMN'], 
                          right_on=['operation','activity','name'],
                          suffixes=['_inflows','_sources'])

    # Assuming all models use US units...
    #source_unit = registries.get_unit_spec('lb/ivld') #Need to be better about naming these
    # if uci.table('GLOBAL')['unit_flag'] == 1:
    #     native_unit = registries.get_unit_spec('lb/ivld') #Need to be better about naming these
    # else:
    #     native_unit = registries.get_unit_spec('kg/ivld') #Need to be better about naming these
    
    #unit_factor, offset = affine_unit_transform(source_unit.measure, target_measure)

    #TODO: optimize as right now I iterrate throug hthe result of the inflows that could be an order of magnitude more than the actual number of timeseries that need specific unit conversion.

    rows = []

    for _, row in result.iterrows():

        inflow_unit = registries.get_unit_spec(row.units_english_inflows)
        #unit_factor, offset = convert(inflow_unit, target_unit)
        unit_factor,offset = affine_unit_transform(inflow_unit.measure, target_unit)
        #TODO: Move COVAL1 override into in topology maybe?, Currently hard coded as a constant in the inflows registry table

        rows.append(PlanRow(
                operation=OperationType(row.SVOL),
                activity=Activity(row.SGRPN),
                opnid=row.SVOLNO,
                variable=row.hbn_name_y,
                unit_spec=inflow_unit,
                scale=float(row.coefficient) * row['effective_factor'] * unit_factor, # important, by not multiplying by the effective factor I am keeping these /acr. Could be a problem since the network transfers don't differentiate between afactr and mfactr... 
                offset = offset + inflow_unit.offset,
                group_by=None
            ))
    return rows


def _pathway_transform(uci, hbn, operation, mlno, ts_name, pathways=None, t_code=4):
    
    tmemn = MASSLINK_SCHEME[ts_name]['tmemn']
    tmemsb1 = MASSLINK_SCHEME[ts_name]['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME[ts_name]['tmemsb2']
    
    masslink = uci.table('MASS-LINK', f'MASS-LINK{mlno}')
    masslink = masslink.loc[
        (masslink['TMEMN'] == tmemn) &
        (masslink['TMEMSB1'] == tmemsb1) &
        (masslink['TMEMSB2'] == tmemsb2)
    ]
    masslink.fillna({'MFACTOR': 1}, inplace=True)
    
    if pathways is not None:
        masslink = masslink.loc[masslink['SMEMN'].isin(pathways)]

    if masslink.empty:
        return None  # <-- consistent "no data" sentinel

    parts = []
    for _, row in masslink.iterrows():
        hbn_name = row['SMEMN']
        if hbn_name in ['IOQUAL', 'SOQUAL', 'POQUAL', 'AOQUAL']:
            qual_name = uci.table(
                operation, 'QUAL-PROPS', int(row['SMEMSB1']) - 1
            ).iloc[0]['QUALID']
            hbn_name = '-'.join([row['SMEMN'], qual_name])
        mfactor = row['MFACTOR']
        parts.append(hbn.get_multiple_timeseries(row['SVOL'], t_code, hbn_name) * mfactor)

    ts = parts[0]
    for part in parts[1:]:
        ts = ts + part

    if ts_name == 'labile_oxygen_demand_phosphorous':
        ts = ts * _BOD_PHOSPHORUS_CONVERSION
    elif ts_name == 'labile_oxygen_demand_nitrogen':
        ts = ts * _BOD_NITROGEN_CONVERSION

    return ts


def get_timeseries(uci, hbn, operation, ts_names, pathways=None, t_code=5):

    subset = uci.table('SCHEMATIC').query('SVOL == @operation')

    totals = []
    for mlno in subset['MLNO'].unique():
        weight = (subset.query('MLNO == @mlno').groupby('SVOLNO')['AFACTR'].sum()/ subset.groupby('SVOLNO')['AFACTR'].sum())

        # Collect per-ts_name results, dropping Nones
        parts = [_pathway_transform(uci, hbn, operation, mlno, ts_name, pathways, t_code)
            for ts_name in ts_names
        ]
        parts = [p for p in parts if p is not None]
        if not parts:
            continue  # <-- nothing to contribute, skip this mlno entirely

        _ts = parts[0]
        for part in parts[1:]:
            _ts = _ts + part

        _ts = _ts[weight.index]
        totals.append(_ts * weight)

    if not totals:
        return pd.DataFrame()  # <-- caller gets a single, predictable type

    ts = pd.concat(totals, axis=1).T.groupby(level=0).sum().T
    return ts

def get_simulated_implnd_constituent(hbn,constituent,time_step):
    """Retrieve a summed impervious-land constituent time-series from an HBN source.

    Looks up the required HBN constituent names for the given
    high-level constituent, retrieves each time-series from *hbn*,
    and returns their sum.  TSS values are converted from tons to
    pounds (×2000).

    Parameters
    ----------
    hbn : hbnInterface or hbnClass
        HBN data source that implements ``get_multiple_timeseries``.
    constituent : str
        High-level constituent abbreviation (e.g. ``'TSS'``, ``'TP'``).
    time_step : int or str
        HSPF time-code or frequency string for the desired output
        interval.

    Returns
    -------
    pandas.DataFrame
        Summed constituent time-series across all IMPLND segments.
    """
    t_cons = constituents.get_tcons(constituent,'IMPLND')
    df = sum([hbn.get_multiple_timeseries(t_opn='IMPLND', 
                                       t_con= t_con, 
                                       t_code = time_step) for t_con in t_cons])
    # df.loc[:,'OPN'] = 'IMPLND'
    # df.columns = ['OPNID',constituent,'SVOL']  
    if constituent == 'TSS':
        df = df*2000

    return df


def get_simulated_perlnd_constituent(hbn,constituent,time_step):
    """Retrieve a summed pervious-land constituent time-series from an HBN source.

    Analogous to :func:`get_simulated_implnd_constituent` but queries
    ``PERLND`` operations.  TSS values are converted from tons to
    pounds (×2000).

    Parameters
    ----------
    hbn : hbnInterface or hbnClass
        HBN data source that implements ``get_multiple_timeseries``.
    constituent : str
        High-level constituent abbreviation (e.g. ``'TSS'``, ``'TP'``).
    time_step : int or str
        HSPF time-code or frequency string for the desired output
        interval.

    Returns
    -------
    pandas.DataFrame
        Summed constituent time-series across all PERLND segments.
    """
    t_cons = constituents.get_tcons(constituent,'PERLND')
    df = sum([hbn.get_multiple_timeseries(t_opn='PERLND', 
                                       t_con= t_con, 
                                       t_code = time_step) for t_con in t_cons])
    # df.loc[:,'OPN'] = 'PERLND'
    # df.columns = ['OPNID',constituent,'SVOL']  
    if constituent == 'TSS':
        df = df*2000

    return df

def get_catchment_constituent(hbn,constituent,catchment_ids = None,time_step = 5):
    """Retrieve per-acre constituent loads for all pervious and impervious lands.

    Combines PERLND and IMPLND outputs into a single long-format
    DataFrame with columns for datetime, operation ID, constituent
    value, operation type, and units.

    Parameters
    ----------
    hbn : hbnInterface or hbnClass
        HBN data source.
    constituent : str
        High-level constituent abbreviation.
    catchment_ids : list of int, optional
        Reserved for future filtering; currently unused.
    time_step : int or str, optional
        HSPF time-code or frequency string (default ``5`` = yearly).

    Returns
    -------
    pandas.DataFrame
        Long-format DataFrame with columns ``'datetime'``,
        ``'OPNID'``, *constituent*, ``'OPERATION'``, and ``'unit'``.
    """
    if constituent == 'Q':
        units = 'in/acre'
    else:
        units = 'lb/acre'
    
    perlnds = hbn.get_perlnd_constituent(constituent).reset_index().melt(id_vars = ['index'],var_name = 'OPNID')
    perlnds['OPERATION'] = 'PERLND'
    implnds = hbn.get_implnd_constituent(constituent).reset_index().melt(id_vars = ['index'],var_name = 'OPNID')
    implnds['OPERATION'] = 'IMPLND'

    df = pd.concat([perlnds,implnds],axis=0)
    df['unit'] = units 
    df.rename(columns = {'index':'datetime','value':constituent},inplace = True)
    return df

        
def get_simulated_flow(hbn,time_step,reach_ids,unit = None):
    """Retrieve simulated streamflow from one or more RCHRES segments.

    Reads the ``ROVOL`` time-series (acre-ft per interval) and converts
    to the requested *unit*.  Negative reach IDs cause the
    corresponding flow to be subtracted (e.g. for split-flow routing).

    Parameters
    ----------
    hbn : hbnInterface or hbnClass
        HBN data source.
    time_step : int or str
        HSPF time-code or frequency string.
    reach_ids : list of int
        Reach segment IDs.  A negative ID means its flow is subtracted.
    unit : {'cfs', 'acrft'}, optional
        Desired output unit (default ``'cfs'``).

    Returns
    -------
    pandas.Series
        Flow time-series with ``attrs['unit']`` set to *unit*.
    """
    
    if unit is None:
        unit = 'cfs'
    assert unit in ['cfs','acrft']

    # if sign is None:
    #     exclude = [1 for i in enumerate(reach_ids)]
    sign = [math.copysign(1,reach_id) for reach_id in reach_ids]
    reach_ids = [abs(reach_id) for reach_id in reach_ids]
    
    flows = hbn.get_multiple_timeseries('RCHRES',time_step,'ROVOL',reach_ids)
    flows = (flows*sign).sum(axis=1) # Correct instances when a flow needs to be subtracted (rare)
    
    if unit == 'cfs':
        flows = flows/CF2CFS[time_step]*43560 #Acrfeet/invl to cubic feet/s
    
    flows.attrs['unit'] = unit
    return flows

def get_simulated_temperature(hbn,time_step,reach_ids):
    """Retrieve simulated water temperature for a single reach.

    Parameters
    ----------
    hbn : hbnInterface or hbnClass
        HBN data source.
    time_step : int or str
        HSPF time-code or frequency string.
    reach_ids : list of int
        Must contain exactly one reach ID.

    Returns
    -------
    pandas.Series
        Water-temperature time-series with ``attrs['unit']`` set to
        ``'degf'``.

    Raises
    ------
    AssertionError
        If *reach_ids* contains more than one element.
    """
    assert len(reach_ids) == 1, "Temperature can only be retreived for one reach at a time."


    wt = hbn.get_multiple_timeseries('RCHRES',time_step,'TW', reach_ids)
    wt = wt.sum(axis=1)
    wt.attrs['unit'] = 'degf'
    
    return wt
    

def get_simulated_reach_constituent(hbn,constituent,time_step,reach_ids,unit = None):
    """Retrieve a simulated reach water-quality constituent.

    Fetches the raw load (lb) time-series for *constituent*, optionally
    converts to concentration (mg/L) using simulated flow, and applies
    sign corrections for negative reach IDs.

    Parameters
    ----------
    hbn : hbnInterface or hbnClass
        HBN data source.
    constituent : str
        High-level constituent abbreviation (e.g. ``'TP'``, ``'TSS'``).
    time_step : int or str
        HSPF time-code or frequency string.
    reach_ids : list of int
        Reach segment IDs.  Negative IDs are subtracted.
    unit : {'mg/l', 'lb'}, optional
        Desired output unit.  Defaults to the value in
        :data:`UNIT_DEFAULTS` for *constituent*.

    Returns
    -------
    pandas.Series
        Constituent time-series with ``attrs`` for ``'unit'``,
        ``'constituent'``, and ``'reach_ids'``.
    """
    # if exclude is None:
    #     exclude = [1 for i in enumerate(reach_ids)]
    sign = [math.copysign(1,reach_id) for reach_id in reach_ids]

    if unit is None:
        unit = UNIT_DEFAULTS[constituent]
    else:
        assert(unit in ['mg/l','lb'])
        
    t_cons = constituents.get_tcons(constituent,'RCHRES','lb')
    
    # Correct instances when a reach output needs to be subtracted (rare)
    df = pd.concat([hbn.get_multiple_timeseries('RCHRES',time_step,t_con,[abs(reach_id) for reach_id in reach_ids])*sign for t_con in t_cons],axis=1).sum(axis=1)
    
    if constituent == 'TSS':
        df = df*2000
    
    
    if unit == 'mg/l':
        #if time_step not in ['h','hourly']:
        flow = get_simulated_flow(hbn,time_step,reach_ids,'acrft')*1233481.8375475 #(acrft to Liters)
        df = df*453592.37 # lbs to mg/l
        df = df/flow
    
    df.attrs['unit'] = unit
    df.attrs['constituent'] = constituent
    df.attrs['reach_ids'] = reach_ids
    return df

#: Conversion factors to translate BOD oxygen demand into equivalent phosphorus and nitrogen mass loadings.
_BOD_PHOSPHORUS_CONVERSION = 0.007326
_BOD_NITROGEN_CONVERSION = 0.052938

#: Mapping of phosphorus species to MASS-LINK table member identifiers.
#:
#: Each key is a phosphorus component name and each value is a dict with
#: ``tmemn`` (target member name), ``tmemsb1`` (target member subscript 1),
#: and ``tmemsb2`` (target member subscript 2) used to look up the
#: corresponding MASS-LINK entry in the UCI file.
MASSLINK_SCHEME = {
    'dissolved_orthophosphate': {'tmemn': 'NUIF1',
                                                'tmemsb1': '4',
                                                'tmemsb2':''},
                'particulate_orthophosphate_sand': {'tmemn': 'NUIF2',
                                                    'tmemsb1': '1',
                                                    'tmemsb2':'2'},
                'particulate_orthophosphate_silt': {'tmemn': 'NUIF2',
                                                    'tmemsb1': '2',
                                                    'tmemsb2':'2'},
                'particulate_orthophosphate_clay': {'tmemn': 'NUIF2',
                                                    'tmemsb1': '3',
                                                    'tmemsb2':'2'},
                'organic_refactory_phosphorous': {'tmemn': 'PKIF',
                                                  'tmemsb1' : '4',
                                                  'tmemsb2':''},
                'organic_refactory_carbon':{'tmemn' : 'PKIF',
                                            'tmemsb1': '5',
                                            'tmemsb2':''},
                'labile_oxygen_demand_phosphorous': {'tmemn': 'OXIF',
                                         'tmemsb1': '2',
                                         'tmemsb2':''},
                'dissolved_total_ammonia': {'tmemn': 'NUIF1',
                                  'tmemsb1': '2',
                                  'tmemsb2':''},
                'dissolved_nitrate': {'tmemn': 'NUIF1',
                                  'tmemsb1': '1',
                                  'tmemsb2':''},
                'organic_refactory_nitrogen': {'tmemn': 'PKIF',
                                         'tmemsb1': '3',
                                         'tmemsb2':''},
                'labile_oxygen_demand_nitrogen': {'tmemn': 'OXIF',
                                         'tmemsb1': '2',
                                         'tmemsb2':'',
                                         }
}

def _calculate_BOD_nitrogen(uci):
    table = uci.table('RCHRES','CONV-VAL1',0)
    conversions = 14* table['BPCNTC']*table['CVBPN']/(12*100*table['CVBPC'] * table['CVBO'])
    conversions.name = 'TN_BOD_CONVERSION'
    return conversions

def _calculate_BOD_phosphorus(uci):
    table = uci.table('RCHRES','CONV-VAL1',0)
    conversions = 31* table['BPCNTC']/(12*100*table['CVBPC'] * table['CVBO'])
    conversions.name = 'TP_BOD_CONVERSION'
    return conversions


def _valid_timeseries():
    """List of valid timeseries names that can be extracted via the MASS-LINK scheme."""
    return list(MASSLINK_SCHEME.keys())

# def get_timeseries(ts_name,uci,hbn,operation,mlno,t_code = 4):
#     """
#     Retrieve and transform modeled timeseries loadings for a given constituent
#     by applying mass-link partitioning factors.

#     This function extracts timeseries data from an HBN (binary output) file for a
#     specified operation and transforms it using the mass-link scheme. This is
#     necessary when direct model outputs from operations (e.g., PERLNDS, IMPLNDS)
#     are partitioned across different pathways via the MASS-LINK block in the UCI
#     file. The mass-link member number determines how the raw output is distributed
#     among receiving targets.

#     Valid timeseries names that can be retrieved are:
#     - 'dissolved_orthophosphate'
#     - 'particulate_orthophosphate_sand'
#     - 'particulate_orthophosphate_silt'
#     - 'particulate_orthophosphate_clay'
#     - 'particulate_orthophosphate'
#     - 'organic_refactory_phosphorous'
#     - 'organic_refactory_carbon'
#     - 'labile_oxygen_demand_phosphorous'
#     - 'dissolved_total_ammonia'
#     - 'dissolved_nitrate'
#     - 'organic_refactory_nitrogen'
#     - 'labile_oxygen_demand_nitrogen'

#     :param ts_name: The name of the timeseries constituent to retrieve, used as
#         a key into the ``MASSLINK_SCHEME`` dictionary to look up the appropriate
#         target member name and sub-member identifiers.
#     :type ts_name: str
#     :param uci: The parsed UCI object containing the
#         model configuration, including mass-link definitions.
#     :type uci: object
#     :param hbn: The HBN file object containing
#         the raw modeled timeseries results.
#     :type hbn: object
#     :param operation: The HSPF operation identifier (e.g., ``'PERLND'``,
#         ``'IMPLND'``) from which the timeseries originates.
#     :type operation: str
#     :param mlno: The MASS-LINK member number that specifies the MASS-LINK table to use when partitioning
#         pathways for the constituent.
#     :type mlno: int
#     :param t_code: The time code specifying the temporal resolution of the
#         output timeseries. Defaults to ``4`` (monthly).
#     :type t_code: int, optional

#     :return: The transformed timeseries loadings after applying the mass-link
#         partitioning factors.
#     :rtype: pandas.Series or pandas.DataFrame
#     """
#     """Calculates timeseries loadings for a given constituent from the operation and MASS-LINK member identifiers."""
    
#     assert ts_name in _valid_timeseries(), f"Invalid timeseries name '{ts_name}'. Valid options are: {_valid_timeseries()}"
    
#     tmemn = MASSLINK_SCHEME[ts_name]['tmemn']
#     tmemsb1 = MASSLINK_SCHEME[ts_name]['tmemsb1']
#     tmemsb2 = MASSLINK_SCHEME[ts_name]['tmemsb2']
#     return _qualprop_transform(uci,hbn,operation,mlno,tmemn,tmemsb1,tmemsb2,t_code)


def total_nitrogen(uci,hbn,t_code,operation = 'PERLND',constituents = None,pathways = None):
    """Compute total nitrogen loading for all OPNIDs in an operation.

    Sums dissolved nitrate, dissolved total ammonia, organic refractory
    nitrogen, and a converted labile oxygen demand component (BOD × 0.052938
    factor) across all MASS-LINK groups.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    t_code : int
        HBN time-step code.
    operation : str, optional
        Operation type (default ``'PERLND'``).

    Returns
    -------
    pd.DataFrame
        Total nitrogen timeseries with OPNID columns and DatetimeIndex.
    """
    if constituents is None:
        constituents = ['dissolved_total_ammonia',
                        'dissolved_nitrate',
                        'organic_refactory_nitrogen',
                        'labile_oxygen_demand_nitrogen']


    opnids = uci.network.subwatersheds()
    opnids = list(set(uci.table('SCHEMATIC').query('TVOL == "RCHRES" & SVOL == @operation')['SVOLNO'].to_list()))
    #opnids = opnids.join(_calculate_BOD_phosphorus(uci).to_frame())
    
    

    total = get_timeseries(uci,hbn,operation,constituents,pathways,t_code)[opnids]
    return total
    

def total_phosphorus(uci,hbn,t_code,operation = 'PERLND',constituents = None,pathways = None):
    """Compute total phosphorus loading for all OPNIDs in an operation.

    Sums dissolved orthophosphate, particulate orthophosphate, organic
    refractory phosphorus, and a converted labile oxygen demand component
    (BOD × 0.007326) across all MASS-LINK groups.

    Parameters
    ----------
    uci : UCI
        Parsed UCI model object.
    hbn : hbnInterface
        HBN binary output interface.
    t_code : int
        HBN time-step code.
    operation : str, optional
        Operation type (default ``'PERLND'``).

    Returns
    -------
    pd.DataFrame
        Total phosphorus timeseries with OPNID columns and DatetimeIndex.
    """
    if constituents is None:
        constituents = ['dissolved_orthophosphate',
                        'particulate_orthophosphate_sand',
                        'particulate_orthophosphate_clay',
                        'particulate_orthophosphate_silt',
                        'organic_refactory_phosphorous',
                        'labile_oxygen_demand_phosphorous']


    opnids = uci.network.subwatersheds()
    opnids = list(set(uci.table('SCHEMATIC').query('TVOL == "RCHRES" & SVOL == @operation')['SVOLNO'].to_list()))
    #opnids = opnids.join(_calculate_BOD_phosphorus(uci).to_frame())
    
    

    total = get_timeseries(uci,hbn,operation,constituents,pathways,t_code)[opnids]
    return total

def _pathway_transform(uci, hbn, operation, mlno, ts_name, pathways=None, t_code=4):
    
    tmemn = MASSLINK_SCHEME[ts_name]['tmemn']
    tmemsb1 = MASSLINK_SCHEME[ts_name]['tmemsb1']
    tmemsb2 = MASSLINK_SCHEME[ts_name]['tmemsb2']
    
    masslink = uci.table('MASS-LINK', f'MASS-LINK{mlno}')
    masslink = masslink.loc[
        (masslink['TMEMN'] == tmemn) &
        (masslink['TMEMSB1'] == tmemsb1) &
        (masslink['TMEMSB2'] == tmemsb2)
    ]
    masslink.fillna({'MFACTOR': 1}, inplace=True)
    
    if pathways is not None:
        masslink = masslink.loc[masslink['SMEMN'].isin(pathways)]

    if masslink.empty:
        return None  # <-- consistent "no data" sentinel

    parts = []
    for _, row in masslink.iterrows():
        hbn_name = row['SMEMN']
        if hbn_name in ['IOQUAL', 'SOQUAL', 'POQUAL', 'AOQUAL']:
            qual_name = uci.table(
                operation, 'QUAL-PROPS', int(row['SMEMSB1']) - 1
            ).iloc[0]['QUALID']
            hbn_name = row['SMEMN'] + qual_name
        mfactor = row['MFACTOR']
        parts.append(hbn.get_multiple_timeseries(row['SVOL'], t_code, hbn_name) * mfactor)

    ts = parts[0]
    for part in parts[1:]:
        ts = ts + part

    if ts_name == 'labile_oxygen_demand_phosphorous':
        ts = ts * _BOD_PHOSPHORUS_CONVERSION
    elif ts_name == 'labile_oxygen_demand_nitrogen':
        ts = ts * _BOD_NITROGEN_CONVERSION

    return ts


def get_timeseries(uci, hbn, operation, ts_names, pathways=None, t_code=5):

    subset = uci.table('SCHEMATIC').query('SVOL == @operation')

    totals = []
    for mlno in subset['MLNO'].unique():
        weight = (subset.query('MLNO == @mlno').groupby('SVOLNO')['AFACTR'].sum()/ subset.groupby('SVOLNO')['AFACTR'].sum())

        # Collect per-ts_name results, dropping Nones
        parts = [_pathway_transform(uci, hbn, operation, mlno, ts_name, pathways, t_code)
            for ts_name in ts_names
        ]
        parts = [p for p in parts if p is not None]
        if not parts:
            continue  # <-- nothing to contribute, skip this mlno entirely

        _ts = parts[0]
        for part in parts[1:]:
            _ts = _ts + part

        _ts = _ts[weight.index]
        totals.append(_ts * weight)

    if not totals:
        return pd.DataFrame()  # <-- caller gets a single, predictable type

    ts = pd.concat(totals, axis=1).T.groupby(level=0).sum().T
    return ts
# %%
