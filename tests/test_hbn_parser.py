# -*- coding: utf-8 -*-
"""
Unit tests for the hbn_parser.py module.

This module tests the low-level HBN binary parsing functions that have been
separated from the data processing logic in hbn.py.

Test Categories:
================
1. Validation Functions:
   - Magic number validation
   - Operation type validation

2. Parsing Functions:
   - Record length calculation
   - Record header parsing
   - Timestamp parsing
   - Data value parsing

3. Data Classes:
   - HbnRecordHeader
   - HbnDataRecord
   - HbnParseResult
"""

import pytest
import numpy as np
from datetime import datetime
from unittest.mock import Mock, patch

# Import the module under test
from hspf import hbn_parser


# =============================================================================
# SECTION 1: CONSTANTS TESTS
# =============================================================================

class TestConstants:
    """Tests for module-level constants."""
    
    def test_magic_number_value(self):
        """Test the HBN magic number constant."""
        assert hbn_parser.HBN_MAGIC_NUMBER == 0xFD
    
    def test_valid_operations_set(self):
        """Test that valid operations include all HSPF operation types."""
        expected = {'PERLND', 'IMPLND', 'RCHRES'}
        assert hbn_parser.VALID_OPERATIONS == expected
    
    def test_record_type_constants(self):
        """Test record type constants."""
        assert hbn_parser.RECORD_TYPE_NAMES == 0
        assert hbn_parser.RECORD_TYPE_DATA == 1
    
    def test_tcode_constants(self):
        """Test time code constants."""
        assert hbn_parser.TCODE_MINUTELY == 1
        assert hbn_parser.TCODE_HOURLY == 2
        assert hbn_parser.TCODE_DAILY == 3
        assert hbn_parser.TCODE_MONTHLY == 4
        assert hbn_parser.TCODE_YEARLY == 5


# =============================================================================
# SECTION 2: VALIDATION FUNCTION TESTS
# =============================================================================

class TestValidateMagicNumber:
    """Tests for the validate_magic_number function."""
    
    def test_valid_magic_number(self):
        """Test validation passes for correct magic number."""
        data = np.array([0xFD, 0x00, 0x00], dtype=np.uint8)
        is_valid, error = hbn_parser.validate_magic_number(data)
        assert is_valid is True
        assert error == ""
    
    def test_invalid_magic_number(self):
        """Test validation fails for incorrect magic number."""
        data = np.array([0x00, 0x00, 0x00], dtype=np.uint8)
        is_valid, error = hbn_parser.validate_magic_number(data)
        assert is_valid is False
        assert "magic number" in error.lower()
    
    def test_empty_file(self):
        """Test validation fails for empty file."""
        data = np.array([], dtype=np.uint8)
        is_valid, error = hbn_parser.validate_magic_number(data)
        assert is_valid is False
        assert "empty" in error.lower()


class TestValidateOperation:
    """Tests for the validate_operation function."""
    
    def test_valid_perlnd(self):
        """Test PERLND is a valid operation."""
        is_valid, error = hbn_parser.validate_operation('PERLND')
        assert is_valid is True
        assert error == ""
    
    def test_valid_implnd(self):
        """Test IMPLND is a valid operation."""
        is_valid, error = hbn_parser.validate_operation('IMPLND')
        assert is_valid is True
        assert error == ""
    
    def test_valid_rchres(self):
        """Test RCHRES is a valid operation."""
        is_valid, error = hbn_parser.validate_operation('RCHRES')
        assert is_valid is True
        assert error == ""
    
    def test_invalid_operation(self):
        """Test invalid operation type fails validation."""
        is_valid, error = hbn_parser.validate_operation('INVALID')
        assert is_valid is False
        assert "alignment error" in error.lower() or "unknown" in error.lower()


# =============================================================================
# SECTION 3: RECORD LENGTH CALCULATION TESTS
# =============================================================================

class TestCalculateRecordLength:
    """Tests for the calculate_record_length function."""
    
    def test_basic_calculation(self):
        """Test basic record length calculation."""
        # Known values that produce a specific result
        # Based on the formula:
        # rc1 = rc1 >> 2
        # rc2 = rc2 * 64 + rc1
        # rc3 = rc3 * 16384 + rc2
        # reclen = rc * 4194304 + rc3 - 24
        
        # Simple case: all zeros except rc1
        rc1, rc2, rc3, rc = 0, 0, 0, 0
        result = hbn_parser.calculate_record_length(rc1, rc2, rc3, rc)
        assert result == -24  # 0 + 0 - 24
    
    def test_bit_shifting(self):
        """Test that bit shifting is applied correctly to rc1."""
        # rc1 = 4 should become 1 after >> 2
        rc1, rc2, rc3, rc = 4, 0, 0, 0
        result = hbn_parser.calculate_record_length(rc1, rc2, rc3, rc)
        assert result == -24 + 1  # rc1 >> 2 = 1


# =============================================================================
# SECTION 4: DATA CLASS TESTS
# =============================================================================

class TestHbnRecordHeader:
    """Tests for the HbnRecordHeader data class."""
    
    def test_data_record_property(self):
        """Test is_data_record property."""
        header = hbn_parser.HbnRecordHeader(
            record_length=100,
            record_type=hbn_parser.RECORD_TYPE_DATA,
            operation='PERLND',
            segment_id=1,
            activity='PWATER'
        )
        assert header.is_data_record is True
        assert header.is_names_record is False
    
    def test_names_record_property(self):
        """Test is_names_record property."""
        header = hbn_parser.HbnRecordHeader(
            record_length=50,
            record_type=hbn_parser.RECORD_TYPE_NAMES,
            operation='RCHRES',
            segment_id=10,
            activity='HYDR'
        )
        assert header.is_names_record is True
        assert header.is_data_record is False


class TestHbnParseResult:
    """Tests for the HbnParseResult data class."""
    
    def test_default_values(self):
        """Test default values for HbnParseResult."""
        result = hbn_parser.HbnParseResult()
        assert result.mapn == {}
        assert result.mapd == {}
        assert result.raw_data is None
        assert result.is_valid is True
        assert result.error_message == ""
    
    def test_custom_values(self):
        """Test setting custom values."""
        mapn = {('PERLND', 1, 'PWATER'): ['PERO', 'SURO']}
        mapd = {('PERLND', 1, 'PWATER', 5): [(100, 200)]}
        raw_data = np.array([0xFD], dtype=np.uint8)
        
        result = hbn_parser.HbnParseResult(
            mapn=mapn,
            mapd=mapd,
            raw_data=raw_data,
            is_valid=True,
            error_message=""
        )
        
        assert result.mapn == mapn
        assert result.mapd == mapd
        assert result.is_valid is True


# =============================================================================
# SECTION 5: TIMESTAMP AND DATA PARSING TESTS
# =============================================================================

class TestParseTimestamp:
    """Tests for the parse_timestamp function."""
    
    def test_basic_timestamp(self):
        """Test parsing a basic timestamp."""
        # Create binary data with: year=2000, month=1, day=15, hour=12 (becomes 11), minute=0
        import struct
        data = struct.pack('5I', 2000, 1, 15, 12, 0)
        data = np.frombuffer(data, dtype=np.uint8)
        
        dt = hbn_parser.parse_timestamp(data, 0)
        
        # Hour is decremented by 1 (HSPF uses 1-based hours)
        assert dt == datetime(2000, 1, 15, 11, 0)
    
    def test_hour_adjustment(self):
        """Test that hour is decremented correctly (HSPF 1-based to 0-based)."""
        import struct
        # Hour = 1 should become 0
        data = struct.pack('5I', 2020, 6, 1, 1, 0)
        data = np.frombuffer(data, dtype=np.uint8)
        
        dt = hbn_parser.parse_timestamp(data, 0)
        
        assert dt.hour == 0


class TestParseDataValues:
    """Tests for the parse_data_values function."""
    
    def test_single_value(self):
        """Test parsing a single float value."""
        import struct
        data = struct.pack('f', 123.456)
        data = np.frombuffer(data, dtype=np.uint8)
        
        values = hbn_parser.parse_data_values(data, 0, 1)
        
        assert len(values) == 1
        assert abs(values[0] - 123.456) < 0.001
    
    def test_multiple_values(self):
        """Test parsing multiple float values."""
        import struct
        data = struct.pack('3f', 1.0, 2.0, 3.0)
        data = np.frombuffer(data, dtype=np.uint8)
        
        values = hbn_parser.parse_data_values(data, 0, 3)
        
        assert len(values) == 3
        assert values == pytest.approx((1.0, 2.0, 3.0), rel=0.001)


# =============================================================================
# SECTION 6: NEXT INDEX CALCULATION TESTS
# =============================================================================

class TestCalculateNextIndex:
    """Tests for the calculate_next_index function."""
    
    def test_short_record(self):
        """Test next index calculation for records < 36 bytes."""
        current = 100
        reclen = 30
        expected = 100 + 30 + 29
        
        result = hbn_parser.calculate_next_index(current, reclen)
        assert result == expected
    
    def test_long_record(self):
        """Test next index calculation for records >= 36 bytes."""
        current = 100
        reclen = 50
        expected = 100 + 50 + 30
        
        result = hbn_parser.calculate_next_index(current, reclen)
        assert result == expected
    
    def test_boundary_36_bytes(self):
        """Test next index calculation at exactly 36 bytes."""
        current = 100
        reclen = 36
        # 36 is not < 36, so use +30
        expected = 100 + 36 + 30
        
        result = hbn_parser.calculate_next_index(current, reclen)
        assert result == expected


# =============================================================================
# SECTION 7: INTEGRATION-READY TESTS (MOCK-BASED)
# =============================================================================

class TestParseHbnFileMocked:
    """Mock-based tests for parse_hbn_file function."""
    
    def test_file_read_error(self):
        """Test handling of file read errors."""
        with patch('numpy.fromfile', side_effect=FileNotFoundError("File not found")):
            result = hbn_parser.parse_hbn_file("nonexistent.hbn")
            
            assert result.is_valid is False
            assert "failed to read" in result.error_message.lower()
    
    def test_invalid_magic_number_returns_error(self):
        """Test that invalid magic number returns proper error."""
        # Create mock data with wrong magic number
        mock_data = np.array([0x00, 0x00, 0x00], dtype=np.uint8)
        
        with patch('numpy.fromfile', return_value=mock_data):
            result = hbn_parser.parse_hbn_file("test.hbn")
            
            assert result.is_valid is False
            assert "magic number" in result.error_message.lower()


class TestReadTimeseriesData:
    """Tests for read_timeseries_data function."""
    
    def test_empty_entries(self):
        """Test handling of empty mapd entries."""
        raw_data = np.array([0xFD], dtype=np.uint8)
        mapd_entries = []
        column_names = ['ROVOL']
        
        times, rows = hbn_parser.read_timeseries_data(raw_data, mapd_entries, column_names)
        
        assert times == []
        assert rows == []


# =============================================================================
# INTEGRATION TESTS DOCUMENTATION
# =============================================================================
"""
INTEGRATION TESTS NEEDED (require actual HBN files):
=====================================================

1. File Parsing Tests:
   - test_parse_valid_hbn_file: Parse a known good HBN file
   - test_parse_empty_file: Handle empty files gracefully
   - test_parse_corrupted_file: Handle corrupted files gracefully

2. Data Extraction Tests:
   - test_extract_all_operations: Verify all operation types are found
   - test_extract_timeseries_data: Verify correct values are extracted
   - test_timestamp_accuracy: Verify timestamps match expected values

3. Round-Trip Tests:
   - Compare parser output with legacy hbnClass output for identical files

These tests require sample HBN files with known contents to be added to 
tests/data/ directory.
"""
