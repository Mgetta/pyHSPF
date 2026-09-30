"""Shared structural vocabulary for HSPF and the pyHSPF lake."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import ClassVar


class OutputLevel(IntEnum):
    """HSPF output levels written to HBN files. 
    2 means "every PIVL intervals" whose true duration is INDELT × PIVL; 3/4/5 are day/month/year 
    For MPCA models, 2 is typically used for hourly outputs."""

    HOURLY = 2
    DAILY = 3
    MONTHLY = 4
    YEARLY = 5


TimeStep = OutputLevel


TIMESTEP_LABELS: dict[OutputLevel, str] = {
    OutputLevel.HOURLY: "hourly",
    OutputLevel.DAILY: "daily",
    OutputLevel.MONTHLY: "monthly",
    OutputLevel.YEARLY: "yearly",
}

PANDAS_FREQ: dict[OutputLevel, str] = {
    OutputLevel.HOURLY: "h",
    OutputLevel.DAILY: "D",
    OutputLevel.MONTHLY: "ME",
    OutputLevel.YEARLY: "YE",
}


class OperationType(str, Enum):
    """UCI operation-type vocabulary."""

    PERLND = "PERLND"
    IMPLND = "IMPLND"
    RCHRES = "RCHRES"
    COPY = "COPY"
    GENER = "GENER"
    PLTGEN = "PLTGEN"
    DISPLY = "DISPLY"
    DURANL = "DURANL"
    MUTSIN = "MUTSIN"
    BMPRAC = "BMPRAC"
    REPORT = "REPORT"


class EntityType(str, Enum):
    """Operation types that own HBN output series."""

    PERLND = "PERLND"
    IMPLND = "IMPLND"
    RCHRES = "RCHRES"


OPERATIONS = tuple(entity_type.value for entity_type in EntityType)
MAX_OPNID = 999


class Activity(str, Enum):
    """HSPF activity/module names used in output blocks."""

    ATEMP = "ATEMP"
    SNOW = "SNOW"
    PWATER = "PWATER"
    SEDMNT = "SEDMNT"
    PSTEMP = "PSTEMP"
    PWTGAS = "PWTGAS"
    PQUAL = "PQUAL"
    MSTLAY = "MSTLAY"
    PEST = "PEST"
    NITR = "NITR"
    PHOS = "PHOS"
    TRACER = "TRACER"
    IWATER = "IWATER"
    SOLIDS = "SOLIDS"
    IWTGAS = "IWTGAS"
    IQUAL = "IQUAL"
    HYDR = "HYDR"
    ADCALC = "ADCALC"
    CONS = "CONS"
    HTRCH = "HTRCH"
    SEDTRN = "SEDTRN"
    GQUAL = "GQUAL"
    OXRX = "OXRX"
    NUTRX = "NUTRX"
    PLANK = "PLANK"
    PHCARB = "PHCARB"


VALID_ACTIVITIES: dict[EntityType, frozenset[Activity]] = {
    EntityType.PERLND: frozenset(
        {
            Activity.ATEMP,
            Activity.SNOW,
            Activity.PWATER,
            Activity.SEDMNT,
            Activity.PSTEMP,
            Activity.PWTGAS,
            Activity.PQUAL,
            Activity.MSTLAY,
            Activity.PEST,
            Activity.NITR,
            Activity.PHOS,
            Activity.TRACER,
        }
    ),
    EntityType.IMPLND: frozenset(
        {
            Activity.ATEMP,
            Activity.SNOW,
            Activity.IWATER,
            Activity.SOLIDS,
            Activity.IWTGAS,
            Activity.IQUAL,
        }
    ),
    EntityType.RCHRES: frozenset(
        {
            Activity.HYDR,
            Activity.ADCALC,
            Activity.CONS,
            Activity.HTRCH,
            Activity.SEDTRN,
            Activity.GQUAL,
            Activity.OXRX,
            Activity.NUTRX,
            Activity.PLANK,
            Activity.PHCARB,
        }
    ),
}


@dataclass(frozen=True)
class Block:
    """Raw HBN output block."""

    entity_type: EntityType
    activity: Activity
    tcode: int


    _VALID_ACTIVITIES: ClassVar[dict[EntityType, frozenset[Activity]]] = (
        VALID_ACTIVITIES
    )

    def __post_init__(self) -> None:
        entity_type = _coerce_enum(EntityType, self.entity_type)
        activity = _coerce_enum(Activity, self.activity)
        object.__setattr__(self, "entity_type", entity_type)
        object.__setattr__(self, "activity", activity)
        object.__setattr__(self, "tcode", int(self.tcode))
        if activity not in self._VALID_ACTIVITIES[entity_type]:
            raise ValueError(f"{activity.value} is not valid for {entity_type.value}")

    @property
    def name(self) -> str:
        return f"{self.entity_type.value.lower()}_{self.activity.value.lower()}"

    @classmethod
    def from_strings(cls, entity_type: str, activity: str, tcode: int) -> "Block":
        return cls(EntityType(entity_type.upper()), Activity(activity.upper()), tcode)


@dataclass(frozen=True)
class EntityRef:
    """Reference to one modeled HSPF entity within a run."""

    entity_type: EntityType
    entity_id: int

    def __post_init__(self) -> None:
        entity_type = _coerce_enum(EntityType, self.entity_type)
        entity_id = int(self.entity_id)
        object.__setattr__(self, "entity_type", entity_type)
        object.__setattr__(self, "entity_id", entity_id)
        if not 1 <= entity_id <= MAX_OPNID:
            raise ValueError(f"entity_id must be between 1 and {MAX_OPNID}")

    @classmethod
    def from_strings(cls, entity_type: str, entity_id: int) -> "EntityRef":
        return cls(EntityType(entity_type.upper()), entity_id)


@dataclass(frozen=True)
class RunRef:
    """Reference to a registered lake run."""

    run_id: str


class TemporalSemantics(str, Enum):
    """HSPF/DSS time-series value semantics."""

    INST_VAL = "INST-VAL"
    PER_AVER = "PER-AVER"
    PER_CUM = "PER-CUM"


class TransformFunction(str, Enum):
    """HSPF time-series transformation functions."""

    SAME = "SAME"
    AVER = "AVER"
    SUM = "SUM"
    DIV = "DIV"
    INTP = "INTP"
    LAST = "LAST"
    MAX = "MAX"
    MIN = "MIN"
    PCT = "PCT"


class UnitSystem(IntEnum):
    """HSPF unit-system codes."""

    ENGLISH = 1
    METRIC = 2


class VariableKind(str, Enum):
    """Physical kind used by the variable lexicon."""

    FLUX = "flux"
    STATE = "state"
    CONCENTRATION = "concentration"
    TEMPERATURE = "temperature"


class AggregationMethod(str, Enum):
    """Curated rollup methods."""

    SUM = "SUM"
    MEAN = "MEAN"
    LAST = "LAST"
    WEIGHTED_MEAN = "WEIGHTED_MEAN"


def _coerce_enum(enum_type: type[Enum], value: Enum | str) -> Enum:
    if isinstance(value, enum_type):
        return value
    return enum_type(str(value).upper())
