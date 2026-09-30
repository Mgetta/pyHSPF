"""Substance and transport vocabulary for HSPF outputs.

For ``SubstancePhase``, ``phase=None`` means HSPF does not distinguish a
transport phase for that member. ``is_total=True`` means the member is HSPF's
sum over separately modeled components; it does not imply temporal aggregation.
``carrier_fraction`` is populated only when a sorbed substance is carried on a
sediment fraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum


class NutrientSpecies(IntEnum):
    NO3 = 1
    TAM = 2
    NO2 = 3
    PO4 = 4


class SedimentFraction(IntEnum):
    SAND = 1
    SILT = 2
    CLAY = 3


class PlanktonMember(IntEnum):
    PHYTO = 1
    ZOO = 2
    ORN = 3
    ORP = 4
    ORC = 5


class OxygenMember(IntEnum):
    DOX = 1
    BOD = 2


class TransportRole(str, Enum):
    CARRIER = "carrier"
    TRANSPORTED = "transported"
    DUAL = "dual"


class TransportPhase(str, Enum):
    DISSOLVED = "dissolved"
    PARTICULATE = "particulate"
    BED = "bed"
    SUSPENDED = "suspended"


class PathwayAssociation(str, Enum):
    SURFACE = "surface"
    INTERFLOW = "interflow"
    GROUNDWATER = "groundwater"
    SEDIMENT = "sediment"


@dataclass(frozen=True)
class SubstancePhase:
    species: Enum | str
    phase: TransportPhase | None = None
    carrier: SedimentFraction | None = None
    is_total: bool = False


SEDIMENT = "sediment" # Constant representing the sediment phase, don't like this fix

MEMBER_SUBSCRIPTS: dict[str, dict[tuple[int, int | None], SubstancePhase]] = {
    "NUST": {
        (1, None): SubstancePhase(NutrientSpecies.NO3, is_total=True),
        (2, None): SubstancePhase(NutrientSpecies.TAM, is_total=True),
        (3, None): SubstancePhase(NutrientSpecies.NO2, is_total=True),
        (4, None): SubstancePhase(NutrientSpecies.PO4, is_total=True),
    },
    "NUIF1": {
        (1, None): SubstancePhase(NutrientSpecies.NO3, TransportPhase.DISSOLVED),
        (2, None): SubstancePhase(NutrientSpecies.TAM, TransportPhase.DISSOLVED),
        (3, None): SubstancePhase(NutrientSpecies.NO2, TransportPhase.DISSOLVED),
        (4, None): SubstancePhase(NutrientSpecies.PO4, TransportPhase.DISSOLVED),
    },
    "TNUIF": {
        (1, None): SubstancePhase(NutrientSpecies.NO3, is_total=True),
        (2, None): SubstancePhase(NutrientSpecies.TAM, is_total=True),
        (3, None): SubstancePhase(NutrientSpecies.NO2, is_total=True),
        (4, None): SubstancePhase(NutrientSpecies.PO4, is_total=True),
    },
    "NUIF2": {
        (1, 1): SubstancePhase(
            NutrientSpecies.TAM, TransportPhase.PARTICULATE, SedimentFraction.SAND
        ),
        (2, 1): SubstancePhase(
            NutrientSpecies.TAM, TransportPhase.PARTICULATE, SedimentFraction.SILT
        ),
        (3, 1): SubstancePhase(
            NutrientSpecies.TAM, TransportPhase.PARTICULATE, SedimentFraction.CLAY
        ),
        (4, 1): SubstancePhase(
            NutrientSpecies.TAM, TransportPhase.PARTICULATE, is_total=True
        ),
        (1, 2): SubstancePhase(
            NutrientSpecies.PO4, TransportPhase.PARTICULATE, SedimentFraction.SAND
        ),
        (2, 2): SubstancePhase(
            NutrientSpecies.PO4, TransportPhase.PARTICULATE, SedimentFraction.SILT
        ),
        (3, 2): SubstancePhase(
            NutrientSpecies.PO4, TransportPhase.PARTICULATE, SedimentFraction.CLAY
        ),
        (4, 2): SubstancePhase(
            NutrientSpecies.PO4, TransportPhase.PARTICULATE, is_total=True
        ),
    },
    "PKIF": {
        # PKIF is intentionally partial as HSPF does not define phyto or zooplankton members.
        (3, None): SubstancePhase(PlanktonMember.ORN),
        (4, None): SubstancePhase(PlanktonMember.ORP),
        (5, None): SubstancePhase(PlanktonMember.ORC),
    },
    "OXIF": {
        (1, None): SubstancePhase(OxygenMember.DOX, TransportPhase.DISSOLVED),
        (2, None): SubstancePhase(OxygenMember.BOD),
    },
    "ISED": {
        (1, None): SubstancePhase(SedimentFraction.SAND, TransportPhase.SUSPENDED),
        (2, None): SubstancePhase(SedimentFraction.SILT, TransportPhase.SUSPENDED),
        (3, None): SubstancePhase(SedimentFraction.CLAY, TransportPhase.SUSPENDED),
        (4, None): SubstancePhase(SEDIMENT, TransportPhase.SUSPENDED, is_total=True),
    },
    # Add outflow counterpart layouts after verifying names in the catalog files.
}


class ReportingConstituent(str, Enum):
    TSS = "TSS"
    TKN = "TKN"
    N = "N"
    TN = "TN"
    OP = "OP"
    TP = "TP"
    BOD = "BOD"
    Q = "Q"
    WT = "WT"
    CHLA = "ChlA"
    DO = "DO"


CONSTITUENT_ROLES: dict[ReportingConstituent, TransportRole] = {
    ReportingConstituent.TSS: TransportRole.DUAL,
    ReportingConstituent.TKN: TransportRole.TRANSPORTED,
    ReportingConstituent.N: TransportRole.TRANSPORTED,
    ReportingConstituent.TN: TransportRole.TRANSPORTED,
    ReportingConstituent.OP: TransportRole.TRANSPORTED,
    ReportingConstituent.TP: TransportRole.TRANSPORTED,
    ReportingConstituent.BOD: TransportRole.TRANSPORTED,
    ReportingConstituent.Q: TransportRole.DUAL,
    ReportingConstituent.WT: TransportRole.DUAL,
    ReportingConstituent.CHLA: TransportRole.TRANSPORTED,
    ReportingConstituent.DO: TransportRole.TRANSPORTED,
}


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


def nutrient_name(nutrient_id: int):
    # Legacy external ids; id 4 historically represents TP reporting even when
    # sourced through a BOD/orthophosphate calculation path.
    key = {0:'TSS',
           1:'TKN',
           2:'N',
           3:'OP',
           4:'TP',# REally this is BOD but you subtract orthophosphate to get BOD
           5:'ChlA',
           6:'DO',
           7: 'Q'} 
    return key[nutrient_id]

def nutrient_id(nutrient_name: str):
    key = {'TSS' :0,
           'TKN' :1,
           'N'   :2,
           'OP'  :3,
           'TP'  :4, # REally this is BOD but you subtract orthophosphate to get BOD
           'ChlA':5,
           'DO'  :6,
           'Q'   :7} 
    return key[nutrient_name]