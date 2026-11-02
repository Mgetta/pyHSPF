"""Substance and transport vocabulary for HSPF outputs.

For ``SubstancePhase``, ``phase=None`` means HSPF does not distinguish a
transport phase for that member. ``is_total=True`` means the member is HSPF's
sum over separately modeled components; it does not imply temporal aggregation.
``carrier_fraction`` is populated only when a sorbed substance is carried on a
sediment fraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum, StrEnum
from typing import Mapping

from hspf.core.types import AggregationMethod, Unit, VariableKind

# HSPF native constituents
# class Constituents(StrEnum):
#     WATER = "water"
#     DO = "do"


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

class Pathway(StrEnum):          # P10 — fact-grain column on component atoms
    SURFACE = "surface"          # SOQUAL-derived
    INTERFLOW = "interflow"      # IOQUAL-derived
    GROUNDWATER = "groundwater"  # AOQUAL-derived
    UNSPLIT = "unsplit"          # model wired the total (POQUAL); never sum with parts

class Basis(StrEnum):            # P9 — whether an AFACTR join is mandatory
    PER_AREA = "per_area"        # land outputs: tons/ac.ivld, in/ivld
    ABSOLUTE = "absolute"        # reach outputs: ton/ivld, ac-ft/ivld

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


SEDIMENT = "sediment"

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