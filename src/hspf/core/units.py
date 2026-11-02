from __future__ import annotations
import calendar
from datetime import datetime
from dataclasses import dataclass
from enum import Enum, StrEnum


'''
Convert a unit's meas



'''



class Unit(StrEnum):
  """Atomic physical and placeholder units for quantity and normalization."""

  # Mass
  G = "g"
  UG = "ug"
  MG = "mg"
  LB = "lb"
  KG = "kg"
  TON = "ton"
  # Length
  IN = "in"
  FT = "ft"
  M = "m"
  # Area
  FT2 = "ft2"
  M2 = "m2"
  ACR = "acr"
  # Volume
  FT3 = "ft3"
  M3 = "m3"
  L = "l"
  ML = "ml"
  ACRFT = "acrft"
  ACRIN = "acrin"
  # Energy, Temperature, Chemistry
  BTU = "BTU"
  J = "J"
  CAL = "cal"
  KCAL = "kcal"
  DEGF = "degF"
  DEGC = "degC"
  PH = "pH"
  # Countable & User-Defined Placeholders
  FRACTION = "fraction"
  ORGANISM = "organism"
  QTY = "qty"
  CONCU = "concu"
  CONCID = "concid"


class Dimension(StrEnum):
    """Physical dimensions for units."""

    MASS = "mass"
    VOLUME = "volume"
    AREA = "area"
    LENGTH = "length"
    HEAT = "heat"
    TEMPERATURE = "temperature"
    ENERGY = "energy"


#custom conversion error
class UnitConversionError(Exception):
    """Custom error for invalid unit conversions."""
    pass

class DimensionConversionError(Exception):
    """Custom error for invalid dimension conversions."""
    pass

class TimeBasis(StrEnum):
  """Temporal denominator basis in units.csv."""

  IVLD = "ivld"
  SECOND = "s"
  HOUR = "h"
  MONTH = "m"
  YEAR = "y"
  DAY = "d"

OUTPUT_BASIS: dict[int, TimeBasis] = {
    2: TimeBasis.HOUR,
    3: TimeBasis.DAY,
    4: TimeBasis.MONTH,
    5: TimeBasis.YEAR,
}

class Period(StrEnum):
  """Reporting/aggregation timestep periods."""

  HOUR = "hour"
  DAY = "day"
  MONTH = "month"
  YEAR = "year"


class UnitTransform:
    """Affine transformation: y = scale * x + offset."""
    scale: float
    offset: float = 0.0

    def __call__(self, value):
        return value * self.scale + self.offset

@dataclass(frozen=True)
class UnitSpec:
  code: str  # HSPF atomic unit string (e.g., "mg/l", "ft3/s", "BTU/ac.ivld")
  measure: Unit | None = None  # Numerator measure (lb, mg, in, ft3, ...)
  normalization: Unit | None = None  # Spatial/carrier denominator (ac, ft2, m2, l, kg, ...)
  dimension: Dimension | None = None  # Physical dimension of the unit (mass, volume, area, length, heat, temperature)
  interval: TimeBasis | None = None  # Time denominator (HSPF tcode: 2=hourly, 3=daily, 4=monthly, 5=yearly)
  offset: float = 0.0  # Offset for affine transformation (used in temperature conversions)
  custom: bool = False  # True if qty, concu, or concid

_CANONICAL_BASE_UNIT: dict[Dimension, Unit] = {
    Dimension.MASS: Unit.G,
    Dimension.VOLUME: Unit.M3,
    Dimension.AREA: Unit.M2,
    Dimension.LENGTH: Unit.M,
    Dimension.ENERGY: Unit.CAL,
    Dimension.TEMPERATURE: Unit.DEGC,
}

# Map each atomic Unit to (dimension, factor_to_canonical_base_unit, offset_to_canonical_base_unit)
_ATOMIC_BASE: dict[Unit, tuple[Dimension, float, float]] = {
    # Mass (base = KG)
    Unit.TON: (Dimension.MASS, 907_184.74,0),
    Unit.LB:  (Dimension.MASS, 453.59237,0),
    Unit.KG:  (Dimension.MASS, 1.0 * 1_000.0,0),
    Unit.G:  (Dimension.MASS, 1,0),
    Unit.MG:  (Dimension.MASS, 1.0 / 1_000.0,0),
    Unit.UG:  (Dimension.MASS, 1.0 / 1_000_000.0,0),
    # Volume (base = M3)
    Unit.ACRFT: (Dimension.VOLUME, 1233.4818375475,0),
    Unit.ACRIN: (Dimension.VOLUME, 1233.4818375475 / 12,0),
    Unit.FT3:   (Dimension.VOLUME, 0.028316846592,0),
    Unit.M3:   (Dimension.VOLUME, 1.0,0),
    Unit.L:     (Dimension.VOLUME, 1.0 / 1_000.0,0),
    Unit.ML: (Dimension.VOLUME, 1.0 / 1_000_000.0,0),
    # Area (base = M2)
    Unit.ACR: (Dimension.AREA, 4046.8564224,0),
    Unit.FT2: (Dimension.AREA, 0.09290304,0),
    Unit.M2:  (Dimension.AREA, 1.0,0),
    # Length (base = M)
    Unit.FT:  (Dimension.LENGTH, 0.3048,0),
    Unit.IN:  (Dimension.LENGTH, 0.0254,0),
    Unit.M:   (Dimension.LENGTH, 1.0,0),
    # Temperature (base = degC)
    Unit.DEGC: (Dimension.TEMPERATURE, 1.0,0),
    Unit.DEGF: (Dimension.TEMPERATURE, 5.0 / 9.0, -32.0),  # Approximate conversion factor to degC
    # Energy (base = CAL) #equivalent to heat content in HSPF
    Unit.CAL: (Dimension.ENERGY, 1.0,0),
    Unit.J: (Dimension.ENERGY, 1.0 / 4.184,0),
    Unit.KCAL: (Dimension.ENERGY, 1_000.0,0),
    Unit.BTU: (Dimension.ENERGY, 0.252164,0),  # Approximate conversion factor to CAL
}

#Physical constants for water in canonical base units (1 m3 = 1,000,000 ml)
WATER_G_PER_M3 = 997_047.02
WATER_CAL_PER_G = 1.0

# 1. Atomic cross-dimension bridges: (source_dim, target_dim) -> (scale, offset)
_ATOMIC_DIMENSION_BRIDGES: dict[tuple[Dimension, Dimension], tuple[float, float]] = {
    (Dimension.VOLUME, Dimension.MASS): (WATER_G_PER_M3, 0.0), 
    (Dimension.MASS, Dimension.VOLUME): (1.0 / WATER_G_PER_M3, 0.0),
}

def convert(source: UnitSpec, target: UnitSpec) -> float:

    factor = 1.0
    offset = 0.0

        # 1. Numerator (quantity) conversion
    if source.measure != target.measure:
        num_scale, num_offset = affine_unit_transform(source.measure, target.measure)
        factor *= num_scale
        offset += num_offset

    # 2. Denominator (normalization) conversion (inverse multiplier)
    if source.normalization != target.normalization:
        if source.normalization is None or target.normalization is None:
            raise DimensionConversionError(
                f"Cannot convert normalization {source.normalization!r} to {target.normalization!r} without a scaling quantity."
            )
        den_scale, _ = affine_unit_transform(source.normalization, target.normalization)
        factor /= den_scale

    return factor, offset


def unit_conversion(source: Unit, target: Unit) -> tuple[float, float]:
    if source == target:
        return 1.0, 0.0
    src_dim, src_factor, src_offset = _ATOMIC_BASE[source]
    tgt_dim, tgt_factor, tgt_offset = _ATOMIC_BASE[target]
    if src_dim != tgt_dim:
        raise UnitConversionError(f"Cannot convert {source!r} ({src_dim}) to {target!r} ({tgt_dim}).")
    
    scale = src_factor / tgt_factor
    offset = (src_offset * scale) - tgt_offset
    return scale, offset

def affine_unit_transform(source: Unit, target: Unit) -> tuple[float, float]:
    """Convert between two atomic units across DIFFERENT dimensions via canonical base units."""
    src_dim, _, _ = _ATOMIC_BASE[source]
    tgt_dim, _, _ = _ATOMIC_BASE[target]

    if src_dim == tgt_dim:
        return unit_conversion(source, target)
    
    if (src_dim, tgt_dim) not in _ATOMIC_DIMENSION_BRIDGES:
        raise DimensionConversionError(
            f"No physical dimension bridge defined between {src_dim!r} and {tgt_dim!r}."
        )

    src_base = _CANONICAL_BASE_UNIT[src_dim]
    tgt_base = _CANONICAL_BASE_UNIT[tgt_dim]
    bridge_factor, bridge_offset = _ATOMIC_DIMENSION_BRIDGES[(src_dim, tgt_dim)]

    # source -> src_base -> tgt_base -> target
    s1, o1 = unit_conversion(source, src_base)
    s2, o2 = unit_conversion(tgt_base, target)
    sb, ob = bridge_factor, bridge_offset

    total_scale = s1 * sb * s2
    total_offset = (o1 * sb * s2) + (ob * s2) + o2
    return total_scale, total_offset

def seconds_in_interval(dt: datetime, tcode: int) -> float:
  """Return exact seconds per timestep for a Python datetime and HSPF tcode."""
  if tcode == 2:  # Hourly
    return 3_600.0
  elif tcode == 3:  # Daily
    return 86_400.0
  elif tcode == 4:  # Monthly (exact calendar days for that specific year/month)
    _, days = calendar.monthrange(dt.year, dt.month)
    return float(days * 86_400)
  elif tcode == 5:  # Yearly (365 or 366 days)
    days = 366.0 if calendar.isleap(dt.year) else 365.0
    return days * 86_400.0
  else:
    raise ValueError(f"Unsupported HSPF tcode: {tcode}")

  


def get_measure_factor(source: Unit, target: Unit) -> float:
    """Retrieve the conversion factor between two atomic measures."""
    if source == target:
        return 1.0
    try:
        return affine_unit_transform(source, target)
    except KeyError:
        raise ValueError(f"No conversion factor found for {source} -> {target}")



def get_unit_factor(
    source: UnitSpec, target: UnitSpec, tcode: int | None = None
) -> float:
    """Compute the scalar factor to convert from `source` UnitSpec to `target` UnitSpec."""
    if source.interval != target.interval:
        raise ValueError(
            "This function does not support temporal rebasing as it requires runtime information about the actual time intervals."
        )

    factor = 1.0

    # 1. Numerator (quantity) conversion
    if source.measure != target.measure:
        num_scale, _ = affine_unit_transform(source.measure, target.measure)
        factor *= num_scale

    # 2. Denominator (normalization) conversion (inverse multiplier)
    if source.normalization != target.normalization:
        if source.normalization is None or target.normalization is None:
            raise DimensionConversionError(
                f"Cannot convert normalization {source.normalization!r} to {target.normalization!r} without a scaling quantity."
            )
        den_scale, _ = affine_unit_transform(source.normalization, target.normalization)
        factor /= den_scale

    return factor


def get_ratio_unit_factor(
    num_unit: UnitSpec, den_unit: UnitSpec, target_unit: UnitSpec, tcode: int | None = None
) -> float:
    """Compute scalar factor to convert (num_unit / den_unit) into target_unit (e.g., mg/l)."""
    if num_unit.interval != den_unit.interval or target_unit.interval is not None:
        raise ValueError("Numerator and denominator intervals must match and cancel out.")

    num_target = UnitSpec(code="", measure=target_unit.measure, interval=num_unit.interval)
    den_target = UnitSpec(code="", measure=target_unit.normalization, interval=den_unit.interval)
    return get_unit_factor(num_unit, num_target, tcode=tcode) / get_unit_factor(den_unit, den_target, tcode=tcode)