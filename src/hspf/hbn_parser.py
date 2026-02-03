# -*- coding: utf-8 -*-
"""
HBN Binary File Parser Module

This module contains low-level binary parsing functions for HSPF Binary (HBN) files.
It is designed to be independent of data processing logic to improve testability
and separate concerns.

The HBN file format stores simulation results from HSPF (Hydrological Simulation
Program - Fortran) in a binary format. Each record contains:
- Magic number (0xFD) at the start
- Record header with length and type information
- Operation type (PERLND, IMPLND, RCHRES)
- Activity identifier
- Time code for the temporal resolution
- Data values (as 32-bit floats)

@author: mfratki
"""

from dataclasses import dataclass, field
from struct import unpack
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np


# =============================================================================
# Constants
# =============================================================================

# Magic number that identifies a valid HBN file
HBN_MAGIC_NUMBER = 0xFD

# Valid operation types in HSPF
VALID_OPERATIONS = {'PERLND', 'IMPLND', 'RCHRES'}

# Record type constants
RECORD_TYPE_NAMES = 0  # data names record
RECORD_TYPE_DATA = 1   # data record

# Header format: 4 bytes for record length parts, 1 byte type, 8 bytes operation, 4 bytes id, 8 bytes activity
HEADER_FORMAT = '4BI8sI8s'
HEADER_SIZE = 28

# Time code meanings
TCODE_MINUTELY = 1
TCODE_HOURLY = 2
TCODE_DAILY = 3
TCODE_MONTHLY = 4
TCODE_YEARLY = 5


# =============================================================================
# Data Classes for Parsed Results
# =============================================================================

@dataclass
class HbnRecordHeader:
    """Represents a parsed HBN record header."""
    record_length: int
    record_type: int
    operation: str
    segment_id: int
    activity: str
    
    @property
    def is_data_record(self) -> bool:
        """Check if this is a data record."""
        return self.record_type == RECORD_TYPE_DATA
    
    @property
    def is_names_record(self) -> bool:
        """Check if this is a names record."""
        return self.record_type == RECORD_TYPE_NAMES


@dataclass
class HbnDataRecord:
    """Represents a parsed HBN data record (time series values)."""
    timestamp: datetime
    values: Tuple[float, ...]
    tcode: int


@dataclass
class HbnParseResult:
    """
    Contains the complete results of parsing an HBN file.
    
    Attributes:
        mapn: Dictionary mapping (operation, id, activity) to list of constituent names
        mapd: Dictionary mapping (operation, id, activity, tcode) to list of (index, reclen) tuples
        raw_data: The raw binary data from the file
        is_valid: Whether the file passed validation
        error_message: Error message if validation failed
    """
    mapn: Dict[Tuple[str, int, str], List[str]] = field(default_factory=dict)
    mapd: Dict[Tuple[str, int, str, int], List[Tuple[int, int]]] = field(default_factory=dict)
    raw_data: Optional[np.ndarray] = None
    is_valid: bool = True
    error_message: str = ""


# =============================================================================
# Validation Functions
# =============================================================================

def validate_magic_number(data: np.ndarray) -> Tuple[bool, str]:
    """
    Validate that the HBN file starts with the correct magic number.
    
    Args:
        data: Raw binary data from the file as a numpy array of bytes.
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(data) == 0:
        return False, "Empty file"
    
    if data[0] != HBN_MAGIC_NUMBER:
        return False, f"BAD HBN FILE - must start with magic number 0x{HBN_MAGIC_NUMBER:02X}, got 0x{data[0]:02X}"
    
    return True, ""


def validate_operation(operation: str) -> Tuple[bool, str]:
    """
    Validate that an operation string is a recognized HSPF operation type.
    
    Args:
        operation: The operation string to validate.
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if operation not in VALID_OPERATIONS:
        return False, f"ALIGNMENT ERROR: Unknown operation '{operation}'"
    return True, ""


# =============================================================================
# Parsing Functions
# =============================================================================

def calculate_record_length(rc1: int, rc2: int, rc3: int, rc: int) -> int:
    """
    Calculate the record length from the 4 bytes in the header.
    
    The record length is encoded across 4 bytes using a specific bit-packing scheme.
    
    Args:
        rc1: First record length byte
        rc2: Second record length byte  
        rc3: Third record length byte
        rc: Fourth record length byte
        
    Returns:
        The calculated record length in bytes.
    """
    rc1 = int(rc1 >> 2)
    rc2 = int(rc2) * 64 + rc1      # 2**6
    rc3 = int(rc3) * 16384 + rc2   # 2**14
    reclen = int(rc) * 4194304 + rc3 - 24  # 2**22
    return reclen


def parse_record_header(data: np.ndarray, index: int) -> Tuple[HbnRecordHeader, int]:
    """
    Parse a single record header from the binary data.
    
    Args:
        data: Raw binary data from the file.
        index: Starting byte index for this record.
        
    Returns:
        Tuple of (HbnRecordHeader, next_index) where next_index is the byte position
        after the header.
    """
    rc1, rc2, rc3, rc, rectype, operation, segment_id, activity = unpack(
        HEADER_FORMAT, data[index:index + HEADER_SIZE]
    )
    
    reclen = calculate_record_length(rc1, rc2, rc3, rc)
    
    # Decode operation and activity strings
    operation = operation.decode('ascii').strip()
    activity = activity.decode('ascii').strip()
    
    header = HbnRecordHeader(
        record_length=reclen,
        record_type=rectype,
        operation=operation,
        segment_id=segment_id,
        activity=activity
    )
    
    return header, index + HEADER_SIZE


def parse_names_record(data: np.ndarray, header: HbnRecordHeader, start_index: int) -> List[str]:
    """
    Parse a names record to extract constituent names.
    
    Args:
        data: Raw binary data from the file.
        header: The already-parsed record header.
        start_index: Starting byte index for the names data (after header).
        
    Returns:
        List of constituent names found in this record.
    """
    names = []
    slen = 0
    i = start_index
    
    while slen < header.record_length:
        ln = unpack('I', data[i + slen: i + slen + 4])[0]
        name_bytes = unpack(f'{ln}s', data[i + slen + 4: i + slen + 4 + ln])[0]
        name = name_bytes.decode('ascii').strip().replace('-', '')
        names.append(name)
        slen += 4 + ln
    
    return names


def parse_data_record_metadata(data: np.ndarray, header_index: int) -> int:
    """
    Extract the time code from a data record.
    
    Args:
        data: Raw binary data from the file.
        header_index: Starting byte index of the record (at header start).
        
    Returns:
        The time code (1-5) indicating temporal resolution.
    """
    # Time code is at offset 32 from record start
    tcode = unpack('I', data[header_index + 32: header_index + 36])[0]
    return tcode


def parse_timestamp(data: np.ndarray, index: int) -> datetime:
    """
    Parse a timestamp from the data record.
    
    Args:
        data: Raw binary data from the file.
        index: Starting byte index of the timestamp (5 integers: yr, mo, dy, hr, mn).
        
    Returns:
        The parsed datetime object.
    """
    yr, mo, dy, hr, mn = unpack('5I', data[index: index + 20])
    hr = hr - 1  # HSPF uses 1-based hours
    dt = datetime(yr, mo, dy, 0, mn) + timedelta(hours=hr)
    return dt


def parse_data_values(data: np.ndarray, index: int, nvals: int) -> Tuple[float, ...]:
    """
    Parse data values from a data record.
    
    Args:
        data: Raw binary data from the file.
        index: Starting byte index of the float values.
        nvals: Number of values to read.
        
    Returns:
        Tuple of float values.
    """
    return unpack(f'{nvals}f', data[index:index + (4 * nvals)])


def calculate_next_index(current_index: int, record_length: int) -> int:
    """
    Calculate the next record's starting index.
    
    The offset depends on the record length due to how records are packed.
    
    Args:
        current_index: Starting index of current record.
        record_length: Length of current record.
        
    Returns:
        Starting index of the next record.
    """
    if record_length < 36:
        return current_index + record_length + 29
    else:
        return current_index + record_length + 30


# =============================================================================
# Main Parsing Function
# =============================================================================

def parse_hbn_file(filepath: str) -> HbnParseResult:
    """
    Parse an HBN file and return the mapping structures.
    
    This is the main entry point for parsing HBN files. It reads the binary data
    and builds the mapn (names) and mapd (data locations) dictionaries.
    
    Args:
        filepath: Path to the HBN file to parse.
        
    Returns:
        HbnParseResult containing the parsed data structures.
    """
    from numpy import fromfile
    
    result = HbnParseResult()
    
    # Read raw data
    try:
        result.raw_data = fromfile(filepath, 'B')
    except Exception as e:
        result.is_valid = False
        result.error_message = f"Failed to read file: {str(e)}"
        return result
    
    # Validate magic number
    is_valid, error_msg = validate_magic_number(result.raw_data)
    if not is_valid:
        result.is_valid = False
        result.error_message = error_msg
        return result
    
    # Parse file structure
    mapn = defaultdict(list)
    mapd = defaultdict(list)
    
    data = result.raw_data
    index = 1  # Skip magic number
    
    while index < len(data):
        try:
            # Parse header
            header, data_start = parse_record_header(data, index)
            
            # Validate operation
            is_valid, error_msg = validate_operation(header.operation)
            if not is_valid:
                # Log error but continue parsing
                print(error_msg)
            
            key = (header.operation, header.segment_id, header.activity)
            
            if header.is_data_record:
                tcode = parse_data_record_metadata(data, index)
                mapd[key + (tcode,)].append((index, header.record_length))
                
            elif header.is_names_record:
                names = parse_names_record(data, header, data_start)
                mapn[key].extend(names)
            else:
                print(f'UNKNOWN RECTYPE: {header.record_type}')
            
            # Move to next record
            index = calculate_next_index(index, header.record_length)
            
        except Exception as e:
            result.is_valid = False
            result.error_message = f"Parse error at index {index}: {str(e)}"
            return result
    
    result.mapn = dict(mapn)
    result.mapd = dict(mapd)
    
    return result


def read_timeseries_data(
    raw_data: np.ndarray,
    mapd_entries: List[Tuple[int, int]],
    column_names: List[str]
) -> Tuple[List[datetime], List[Tuple[float, ...]]]:
    """
    Read time series data from the raw binary data.
    
    This function extracts timestamps and values for a specific time series
    from the raw binary data using the pre-built mapd index.
    
    Args:
        raw_data: Raw binary data from the file.
        mapd_entries: List of (index, reclen) tuples for this time series.
        column_names: List of constituent names for this time series.
        
    Returns:
        Tuple of (timestamps, rows) where timestamps is a list of datetime objects
        and rows is a list of tuples containing the float values for each timestep.
    """
    times = []
    rows = []
    nvals = len(column_names)
    
    for (index, reclen) in mapd_entries:
        # Parse timestamp (at offset 36 from record start)
        dt = parse_timestamp(raw_data, index + 36)
        times.append(dt)
        
        # Parse data values (at offset 56 from record start)
        row = parse_data_values(raw_data, index + 56, nvals)
        rows.append(row)
    
    return times, rows
