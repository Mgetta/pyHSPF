"""
Reporting constituents, forms, and their semantics for HSPF outputs.


"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum, StrEnum
from typing import Mapping
from operator import add, mul

from hspf.core.types import AggregationMethod, VariableKind

from enum import StrEnum
'''
total_phosphorus (for a single rchres/perlnd)
 - rchres (outflow from reach)
    - conc
     - PTOTCONC
    - load
     - PTOTOUT
 - perlnd (outflow from perlnd)
    - load
        - dissolved_orthophosphate
            - dissolved_orthophosphate_interflow
            - dissolved_orthophosphate_surface
            - dissolved_orthophosphate_ground
        - particulate_orthophosphate
            - particulate_orthophosphate_sand
            - particulate_orthophosphate_silt
            - particulate_orthophosphate_clay
        - organic_refactory_phosphorous
        - organic_refactory_carbon
        - labile_oxygen_demand
            - labile_oxygen_demand_phosphorus


'''

class ReportingConstituent(StrEnum):
    def __new__(cls, value, display_name, short_code):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.display_name = display_name
        obj.code = short_code
        return obj

    # Format: (API Value, Human-Readable Display Name, Code)
    TOTAL_PHOSPHORUS = ('total_phosphorus', 'Total Phosphorus', 'TP')
    TOTAL_NITROGEN = ('total_nitrogen', 'Total Nitrogen', 'TN')
    TOTAL_AMMONIA = ('total_ammonia', 'Total Ammonia', 'TAM')
    SEDIMENT = ('sediment', 'Sediment', 'SED')
    ORTHOPHOSPHATE = ('orthophosphate', 'Orthophosphate', 'PO4')
    NITRATE = ('nitrate', 'Nitrate', 'NO3')
    NITRITE = ('nitrite', 'Nitrite', 'NO2')
    NITRATE_NITRITE = ('nitrate_nitrite', 'Nitrate + Nitrite', 'NN')
    AMMONIA = ('ammonia', 'Ammonia', 'NH3')
    TOTAL_KJELDAHL_NITROGEN = ('total_kjeldahl_nitrogen', 'Total Kjeldahl Nitrogen', 'TKN')
    BIOCHEMICAL_OXYGEN_DEMAND = ('biochemical_oxygen_demand', 'Biochemical Oxygen Demand', 'BOD')
    DISSOLVED_OXYGEN = ('dissolved_oxygen', 'Dissolved Oxygen', 'DO')
    CHLOROPHYLL_A = ('chlorophyll_a', 'Chlorophyll a', 'CHLA')
    WATER_TEMPERATURE = ('water_temperature', 'Water Temperature', 'WT')
    WATER = ('water', 'Water', 'W')
    DISSOLVED_ORTHOPHOSPHATE = ('dissolved_orthophosphate', 'Dissolved Orthophosphate', 'DOP')
    PARTICULATE_ORTHOPHOSPHATE_SAND = ('particulate_orthophosphate_sand', 'Particulate Orthophosphate (Sand)', 'PO4SAND')
    PARTICULATE_ORTHOPHOSPHATE_SILT = ('particulate_orthophosphate_silt', 'Particulate Orthophosphate (Silt)', 'PO4SILT')
    PARTICULATE_ORTHOPHOSPHATE_CLAY = ('particulate_orthophosphate_clay', 'Particulate Orthophosphate (Clay)', 'PO4CLAY')
    PARTICULATE_ORTHOPHOSPHATE = ('particulate_orthophosphate', 'Particulate Orthophosphate', 'PO4P')
    ORGANIC_REFRACTORY_PHOSPHORUS = ('organic_refactory_phosphorus', 'Organic Refractory Phosphorus', 'ORP')
    ORGANIC_REFRACTORY_CARBON = ('organic_refractory_carbon', 'Organic Refractory Carbon', 'ORC')
    LABILE_OXYGEN_DEMAND_PHOSPHORUS = ('labile_oxygen_demand_phosphorus', 'Labile Oxygen Demand Phosphorus', 'LODP')
    DISSOLVED_TOTAL_AMMONIA = ('dissolved_total_ammonia', 'Dissolved Total Ammonia', 'DTA')
    DISSOLVED_NITRATE = ('dissolved_nitrate', 'Dissolved Nitrate', 'DNO3')
    ORGANIC_REFRACTORY_NITROGEN = ('organic_refractory_nitrogen', 'Organic Refractory Nitrogen', 'ORN')
    LABILE_OXYGEN_DEMAND_NITROGEN = ('labile_oxygen_demand_nitrogen', 'Labile Oxygen Demand Nitrogen', 'LODN')

    @classmethod
    def _missing_(cls, value):
        """Allows lookup by short code (e.g., 'TP') or display name."""
        if not isinstance(value, str):
            return super()._missing_(value)
            
        val_upper = value.upper()
        val_lower = value.lower()
        
        for member in cls:
            if (member.value == val_lower or 
                member.code == val_upper or 
                member.display_name.lower() == val_lower):
                return member
                
        return super()._missing_(value)

class FormType(StrEnum):
    """Mathematical archetype governing spatial and temporal aggregation."""

    # 1. Additive over both space (reaches/segments) and time (ivld)
    EXTENSIVE_FLUX = "extensive_flux"                  # load (lb/ivld), flow (acr.ft/ivld, ft3/s), heat (BTU/ivld)

    # 2. Additive over space, averaged (or last-value) over time
    EXTENSIVE_STATE = "extensive_state"                # volume (acr.ft)

    # 3. Non-additive over space (refuse multi-reach), averaged over time
    INTENSIVE_STATE = "intensive_state"                # depth (ft), single-reach conc/temp state

    # 4. Ratio of extensive flux to water flux: sum(num) / sum(flow)
    FLOW_WEIGHTED_INTENSIVE = "flow_weighted_intensive"  # conc (mg/l), multi-reach/pathway temp (degF)

    # 5. Ratio of extensive flux to contributing area: sum(num) / sum(area)
    AREA_NORMALIZED_FLUX = "area_normalized_flux"      # yield (lb/acr.ivld, in/ivld)

class Form(StrEnum):
    CONC = "conc"
    LOAD = "load"
    YIELD = "yield"      #Load (or Water Flow) normalized by contributing area (acr)
    FLOW = "flow"
    TEMP = "temp"
    VOLUME = "volume"
    DEPTH = "depth"
    AREA = "area"        #Internal/denominator form for contributing land area (AFACTR)

@dataclass(frozen=True)
class FormSemantics:
    kind: VariableKind
    spatial_agg: AggregationMethod | None = AggregationMethod.SUM
    extensive_pair: tuple[Form, Form] | None = None

    @property
    def temporal_agg(self) -> AggregationMethod:
        """Derived automatically from kind — no manual duplication."""
        return AggregationMethod.SUM if self.kind == VariableKind.FLUX else AggregationMethod.MEAN
    
FORM_SEMANTICS: dict[Form, FormSemantics] = {
    # Primitive extensive fluxes (temporal=SUM, spatial=SUM, ratio=None)
    Form.LOAD:   FormSemantics(VariableKind.FLUX,  AggregationMethod.SUM, None),
    Form.FLOW:   FormSemantics(VariableKind.FLUX,  AggregationMethod.SUM, None),

    # Primitive states (temporal=MEAN, ratio=None; VOLUME sums across space, DEPTH does not)
    Form.VOLUME: FormSemantics(VariableKind.STATE, AggregationMethod.SUM, None),
    Form.DEPTH:  FormSemantics(VariableKind.STATE, None,                  None),

    # Intensive ratios (spatial/temporal rollup sums the extensive_pair components first)
    Form.CONC:   FormSemantics(VariableKind.STATE, AggregationMethod.SUM, (Form.LOAD, Form.FLOW)),
    Form.TEMP:   FormSemantics(VariableKind.STATE, AggregationMethod.SUM, (Form.LOAD, Form.FLOW)),
    Form.YIELD:  FormSemantics(VariableKind.FLUX,  AggregationMethod.SUM, (Form.LOAD, Form.AREA)),
}

def reporting_constituent(value: ReportingConstituent | str) -> ReportingConstituent:
    """Return the reporting constituent enum for a key or display value."""

    if isinstance(value, ReportingConstituent):
        return value
    normalized = value.strip()
    for constituent in ReportingConstituent:
        if normalized.upper() in {constituent.name.upper(), constituent.value.upper()}:
            return constituent
    raise ValueError(f"Reporting constituent {value!r} is not recognized.")


def get_tcons(nutrient_name,operation,units = 'mg/l'):
    ''' Convience function for getting the consntituent time series names associated with the nutrients we are
    calibrating for. Note tehat Qual Prop 4 (BOD)
    '''
    
    if operation == 'RCHRES':
        MAP = {'mg/l':{'TSS' :['SSEDTOT'], # TSS
                  'TKN' :['TAMCONCDIS','NTOTORGCONC'], # TKN
                  'N' :['NO2CONCDIS','NO3CONCDIS'], # N
                  'TN': ['NTOTCONCDIS'], # Total Nitrogen
                  'OP' :['PO4CONCDIS'], # Ortho
                  'TP' :['PTOTCONC']},# BOD is the difference of ptot and ortho
         'lb': {'TSS' :['ROSEDTOT'], # TSS
                  'TKN' :['TAMOUTTOT','NTOTORGOUT'], # TKN
                  'N' :['NO3OUTTOT','NO2OUTTOT'], # N
                  'TN': ['NTOTOUT'], # Total Nitrogen
                  'OP' :['PO4OUTDIS'], # Ortho
                  'TP' :['PTOTOUT'],
                  'BOD' :['BODOUTTOT'],},
        'cfs': {'Q': ['ROVOL']},
        'acrft' : {'Q': ['ROVOL']},
        'degf' : {'WT': ['TW']}}
        
        t_cons = MAP[units]
    elif operation == 'PERLND':
        t_cons = {'TSS' :['SOSED'],
                  'TKN' :['POQUALNH3+NH4'],
                  'N' :['POQUALNO3'],
                  'OP' :['POQUALORTHO P'],
                  'BOD' :['POQUALBOD'],
                  'Q' : ['PERO']} # BOD is the difference of ptot and ortho
    elif operation == 'IMPLND':
        t_cons = {'TSS' :['SOSLD'],
                  'TKN' :['SOQUALNH3+NH4'],
                  'N' :['SOQUALNO3'],
                  'OP' :['SOQUALORTHO P'],
                  'BOD' :['SOQUALBOD'],
                  'Q' : ['SURO']} # BOD is the difference of ptot and ortho
    else:
        raise ValueError(f'Operation {operation} not recognized for nutrient time constituent lookup.')
    return t_cons[nutrient_name]

