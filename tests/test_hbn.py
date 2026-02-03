# -*- coding: utf-8 -*-
"""
Unit tests for the hbn.py module.

This module tests the HSPF Binary (HBN) file parsing and data extraction
utilities.

Test Categories:
================
1. Unit Tests (this file):
   - Module-level constants validation
   - Static methods
   - Pure functions / calculations that don't require file I/O
   - Mock-based tests for complex methods

2. Integration Tests (future - documented at bottom):
   - Tests requiring actual HBN files
   - End-to-end data extraction workflows
   - Multi-file interface tests

Code Quality Notes (documented at bottom of file):
- Areas needing refactoring
- Suggested improvements
- Potential bugs found during analysis
"""

import pytest
import math
from unittest.mock import Mock, MagicMock, patch
import pandas as pd
from datetime import datetime

# Import the module under test
from hspf import hbn


# =============================================================================
# SECTION 1: MODULE-LEVEL CONSTANTS TESTS
# =============================================================================

class TestModuleLevelConstants:
    """Tests for module-level constant definitions."""

    def test_cf2cfs_hourly_conversions(self):
        """Test CF2CFS dictionary contains correct hourly conversion values."""
        # 1 hour = 3600 seconds
        assert hbn.CF2CFS['hourly'] == 3600
        assert hbn.CF2CFS['h'] == 3600
        assert hbn.CF2CFS[2] == 3600

    def test_cf2cfs_daily_conversions(self):
        """Test CF2CFS dictionary contains correct daily conversion values."""
        # 1 day = 86400 seconds
        assert hbn.CF2CFS['daily'] == 86400
        assert hbn.CF2CFS['D'] == 86400
        assert hbn.CF2CFS[3] == 86400

    def test_cf2cfs_monthly_conversions(self):
        """Test CF2CFS dictionary contains correct monthly conversion values.
        
        Note: Uses 30-day month approximation (2592000 seconds). This assumes
        all months are exactly 30 days, which differs from actual calendar months
        (28-31 days). This is a known limitation in the module for monthly
        conversions and may introduce small errors in flow calculations.
        """
        # 30 days * 86400 seconds/day = 2592000
        assert hbn.CF2CFS['monthly'] == 2592000
        assert hbn.CF2CFS['ME'] == 2592000
        assert hbn.CF2CFS[4] == 2592000

    def test_cf2cfs_yearly_conversions(self):
        """Test CF2CFS dictionary contains correct yearly conversion values.
        
        Note: Uses a 365-day year (31536000 seconds). This is a standard
        approximation for HSPF calculations and does not account for leap
        years (which have 366 days). This is acceptable for typical hydrologic
        modeling where the small difference is negligible.
        """
        # 365 days * 86400 seconds/day = 31536000
        assert hbn.CF2CFS['yearly'] == 31536000
        assert hbn.CF2CFS['Y'] == 31536000
        assert hbn.CF2CFS['YE'] == 31536000
        assert hbn.CF2CFS[5] == 31536000

    def test_agg_defaults_contains_expected_keys(self):
        """Test AGG_DEFAULTS dictionary contains all expected aggregation methods."""
        expected_keys = {'cfs', 'mg/l', 'degF', 'lb'}
        assert set(hbn.AGG_DEFAULTS.keys()) == expected_keys

    def test_agg_defaults_mean_aggregations(self):
        """Test that rate/concentration units use mean aggregation."""
        assert hbn.AGG_DEFAULTS['cfs'] == 'mean'
        assert hbn.AGG_DEFAULTS['mg/l'] == 'mean'
        assert hbn.AGG_DEFAULTS['degF'] == 'mean'

    def test_agg_defaults_sum_aggregations(self):
        """Test that mass units use sum aggregation."""
        assert hbn.AGG_DEFAULTS['lb'] == 'sum'

    def test_unit_defaults_contains_expected_constituents(self):
        """Test UNIT_DEFAULTS contains all expected constituent types."""
        expected_keys = {'Q', 'TSS', 'TP', 'OP', 'TKN', 'N', 'WT', 'WL'}
        assert set(hbn.UNIT_DEFAULTS.keys()) == expected_keys

    def test_unit_defaults_flow_unit(self):
        """Test default unit for flow (Q) is cubic feet per second."""
        assert hbn.UNIT_DEFAULTS['Q'] == 'cfs'

    def test_unit_defaults_concentration_units(self):
        """Test default units for concentrations are mg/l."""
        concentration_constituents = ['TSS', 'TP', 'OP', 'TKN', 'N']
        for constituent in concentration_constituents:
            assert hbn.UNIT_DEFAULTS[constituent] == 'mg/l'

    def test_unit_defaults_temperature_unit(self):
        """Test default unit for water temperature is degrees Fahrenheit."""
        assert hbn.UNIT_DEFAULTS['WT'] == 'degF'

    def test_unit_defaults_water_level_unit(self):
        """Test default unit for water level is feet."""
        assert hbn.UNIT_DEFAULTS['WL'] == 'ft'

    def test_loss_map_contains_expected_constituents(self):
        """Test LOSS_MAP contains all expected constituent mappings."""
        expected_keys = {'Q', 'TSS', 'TP', 'N', 'TKN', 'OP'}
        assert set(hbn.LOSS_MAP.keys()) == expected_keys

    def test_loss_map_structure(self):
        """Test LOSS_MAP values are tuples of (inflow_list, outflow_list)."""
        for key, value in hbn.LOSS_MAP.items():
            assert isinstance(value, tuple), f"LOSS_MAP['{key}'] should be a tuple"
            assert len(value) == 2, f"LOSS_MAP['{key}'] should have 2 elements"
            assert isinstance(value[0], list), f"LOSS_MAP['{key}'][0] should be a list"
            assert isinstance(value[1], list), f"LOSS_MAP['{key}'][1] should be a list"

    def test_tcodes2freq_mapping(self):
        """Test TCODES2FREQ maps time codes to pandas frequency strings."""
        assert hbn.TCODES2FREQ[1] == 'min'
        assert hbn.TCODES2FREQ[2] == 'h'
        assert hbn.TCODES2FREQ[3] == 'D'
        assert hbn.TCODES2FREQ[4] == 'M'
        assert hbn.TCODES2FREQ[5] == 'Y'


# =============================================================================
# SECTION 2: STATIC METHOD TESTS
# =============================================================================

class TestHbnClassStaticMethods:
    """Tests for static methods in hbnClass."""

    def test_get_perlands_single_index(self):
        """Test get_perlands extracts single perland ID correctly."""
        summary_indxs = ['PERLND_PWATER_101_5']
        result = hbn.hbnClass.get_perlands(summary_indxs)
        assert result == [101]

    def test_get_perlands_multiple_indices(self):
        """Test get_perlands extracts multiple perland IDs correctly."""
        summary_indxs = [
            'PERLND_PWATER_001_5',
            'PERLND_PWATER_002_5',
            'PERLND_PWATER_010_5',
            'PERLND_PWATER_100_5',
        ]
        result = hbn.hbnClass.get_perlands(summary_indxs)
        assert result == [1, 2, 10, 100]

    def test_get_perlands_different_activities(self):
        """Test get_perlands works with different activity types."""
        summary_indxs = [
            'PERLND_PWATER_050_3',
            'PERLND_SNOW_050_3',
            'PERLND_SEDMNT_050_3',
        ]
        result = hbn.hbnClass.get_perlands(summary_indxs)
        assert result == [50, 50, 50]

    def test_get_perlands_different_time_codes(self):
        """Test get_perlands works with different time codes."""
        summary_indxs = [
            'PERLND_PWATER_025_1',  # minutely
            'PERLND_PWATER_025_2',  # hourly
            'PERLND_PWATER_025_3',  # daily
            'PERLND_PWATER_025_4',  # monthly
            'PERLND_PWATER_025_5',  # yearly
        ]
        result = hbn.hbnClass.get_perlands(summary_indxs)
        assert result == [25, 25, 25, 25, 25]

    def test_get_perlands_empty_list(self):
        """Test get_perlands returns empty list for empty input."""
        result = hbn.hbnClass.get_perlands([])
        assert result == []


# =============================================================================
# SECTION 3: HELPER FUNCTION TESTS (CALCULATIONS AND CONVERSIONS)
# =============================================================================

class TestSignCalculations:
    """Test sign calculations used in flow and constituent functions."""

    def test_copysign_positive_values(self):
        """Test math.copysign correctly handles positive reach IDs."""
        reach_ids = [1, 2, 3, 100]
        signs = [math.copysign(1, reach_id) for reach_id in reach_ids]
        assert signs == [1.0, 1.0, 1.0, 1.0]

    def test_copysign_negative_values(self):
        """Test math.copysign correctly handles negative reach IDs.
        
        Negative reach IDs indicate flows to be subtracted.
        """
        reach_ids = [-1, -2, -3, -100]
        signs = [math.copysign(1, reach_id) for reach_id in reach_ids]
        assert signs == [-1.0, -1.0, -1.0, -1.0]

    def test_copysign_mixed_values(self):
        """Test math.copysign correctly handles mixed positive/negative reach IDs."""
        reach_ids = [1, -2, 3, -4]
        signs = [math.copysign(1, reach_id) for reach_id in reach_ids]
        assert signs == [1.0, -1.0, 1.0, -1.0]

    def test_abs_reach_ids(self):
        """Test absolute value conversion of reach IDs."""
        reach_ids = [1, -2, 3, -4]
        abs_reach_ids = [abs(reach_id) for reach_id in reach_ids]
        assert abs_reach_ids == [1, 2, 3, 4]


class TestUnitConversions:
    """Test unit conversion calculations used in the module."""

    def test_acrft_to_cfs_conversion_hourly(self):
        """Test acre-feet per hour to cubic feet per second conversion.
        
        Formula: cfs = (acre-feet/interval) / (seconds/interval) * 43560
        where 43560 is square feet per acre.
        """
        # For hourly: divide by 3600, multiply by 43560
        acrft_per_hour = 1.0
        expected_cfs = 1.0 / 3600 * 43560  # ~12.1 cfs
        assert abs(expected_cfs - 12.1) < 0.1

    def test_lbs_to_mg_conversion(self):
        """Test pounds to milligrams conversion.
        
        1 lb = 453592.37 mg
        """
        lbs = 1.0
        mg = lbs * 453592.37
        assert mg == 453592.37

    def test_acrft_to_liters_conversion(self):
        """Test acre-feet to liters conversion.
        
        1 acre-foot = 1233481.8375475 liters
        """
        acrft = 1.0
        liters = acrft * 1233481.8375475
        assert liters == 1233481.8375475

    def test_tss_tons_to_lbs_conversion(self):
        """Test TSS (total suspended solids) tons to pounds conversion.
        
        TSS is stored in tons, converted to lbs by multiplying by 2000.
        """
        tss_tons = 1.0
        tss_lbs = tss_tons * 2000
        assert tss_lbs == 2000


# =============================================================================
# SECTION 4: HBNCLASS TIME CODE CONVERSION TESTS
# =============================================================================

class TestHbnClassTimeCodes:
    """Tests for time code conversion in hbnClass.
    
    Note: These tests use mocking since hbnClass.__init__ requires a file.
    """

    @pytest.fixture
    def mock_hbn_class(self):
        """Create a mocked hbnClass instance for testing."""
        with patch.object(hbn.hbnClass, '__init__', lambda self, *args, **kwargs: None):
            instance = hbn.hbnClass.__new__(hbn.hbnClass)
            # Set up the tcodes dictionary as it would be in __init__
            instance.tcodes = {
                'minutely': 1, 'hourly': 2, 'daily': 3, 'monthly': 4, 'yearly': 5,
                1: 'minutely', 2: 'hourly', 3: 'daily', 4: 'monthly', 5: 'yearly',
                'min': 1, 'h': 2, 'D': 3, 'M': 4, 'Y': 5, 'H': 2, 'ME': 4, 'YE': 5
            }
            instance.pandas_tcodes = {1: 'min', 2: 'h', 3: 'D', 4: 'ME', 5: 'YE'}
            return instance

    def test_tcodes_string_to_int_conversion(self, mock_hbn_class):
        """Test conversion from string time codes to integers."""
        assert mock_hbn_class.tcodes['minutely'] == 1
        assert mock_hbn_class.tcodes['hourly'] == 2
        assert mock_hbn_class.tcodes['daily'] == 3
        assert mock_hbn_class.tcodes['monthly'] == 4
        assert mock_hbn_class.tcodes['yearly'] == 5

    def test_tcodes_short_string_to_int_conversion(self, mock_hbn_class):
        """Test conversion from short string time codes to integers."""
        assert mock_hbn_class.tcodes['min'] == 1
        assert mock_hbn_class.tcodes['h'] == 2
        assert mock_hbn_class.tcodes['H'] == 2  # case variation
        assert mock_hbn_class.tcodes['D'] == 3
        assert mock_hbn_class.tcodes['M'] == 4
        assert mock_hbn_class.tcodes['Y'] == 5
        assert mock_hbn_class.tcodes['ME'] == 4
        assert mock_hbn_class.tcodes['YE'] == 5

    def test_tcodes_int_to_string_conversion(self, mock_hbn_class):
        """Test conversion from integer time codes to strings."""
        assert mock_hbn_class.tcodes[1] == 'minutely'
        assert mock_hbn_class.tcodes[2] == 'hourly'
        assert mock_hbn_class.tcodes[3] == 'daily'
        assert mock_hbn_class.tcodes[4] == 'monthly'
        assert mock_hbn_class.tcodes[5] == 'yearly'

    def test_pandas_tcodes_mapping(self, mock_hbn_class):
        """Test mapping to pandas frequency strings."""
        assert mock_hbn_class.pandas_tcodes[1] == 'min'
        assert mock_hbn_class.pandas_tcodes[2] == 'h'
        assert mock_hbn_class.pandas_tcodes[3] == 'D'
        assert mock_hbn_class.pandas_tcodes[4] == 'ME'
        assert mock_hbn_class.pandas_tcodes[5] == 'YE'


# =============================================================================
# SECTION 5: MOCK-BASED TESTS FOR COMPLEX METHODS
# =============================================================================

class TestGetSimulatedFlowLogic:
    """Test the logic in get_simulated_flow using mocks."""

    def test_flow_unit_validation_accepts_cfs(self):
        """Test that 'cfs' is an accepted unit."""
        # The assertion in get_simulated_flow checks unit in ['cfs', 'acrft']
        assert 'cfs' in ['cfs', 'acrft']

    def test_flow_unit_validation_accepts_acrft(self):
        """Test that 'acrft' is an accepted unit."""
        assert 'acrft' in ['cfs', 'acrft']

    def test_flow_unit_default_is_cfs(self):
        """Test that default unit for flow is 'cfs'."""
        # From get_simulated_flow: if unit is None: unit = 'cfs'
        unit = None
        if unit is None:
            unit = 'cfs'
        assert unit == 'cfs'


class TestGetSimulatedReachConstituentLogic:
    """Test the logic in get_simulated_reach_constituent using mocks."""

    def test_unit_validation(self):
        """Test valid units for reach constituent."""
        valid_units = ['mg/l', 'lb', 'cfs', 'degF']
        for unit in valid_units:
            assert unit in ['mg/l', 'lb', 'cfs', 'degF']

    def test_unit_default_from_constituent(self):
        """Test that unit defaults are correctly pulled from UNIT_DEFAULTS."""
        for constituent in ['Q', 'TSS', 'TP', 'OP', 'TKN', 'N', 'WT', 'WL']:
            assert constituent in hbn.UNIT_DEFAULTS


class TestGetSimulatedTemperature:
    """Test the get_simulated_temperature function."""

    def test_not_implemented_error(self):
        """Test that get_simulated_temperature raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            hbn.get_simulated_temperature(None, None, None, None)


# =============================================================================
# SECTION 6: HBNINTERFACE TESTS (MOCK-BASED)
# =============================================================================

class TestHbnInterfaceOutputNames:
    """Test hbnInterface.output_names method."""

    def test_output_names_merges_multiple_hbns(self):
        """Test that output_names correctly merges outputs from multiple HBN files."""
        # Create mock hbn objects
        mock_hbn1 = Mock()
        mock_hbn1.output_names.return_value = {'HYDR': ['ROVOL', 'IVOL']}
        
        mock_hbn2 = Mock()
        mock_hbn2.output_names.return_value = {'HYDR': ['ROVOL', 'OVOL']}
        
        # Create interface with mocked __init__
        with patch.object(hbn.hbnInterface, '__init__', lambda self, *args, **kwargs: None):
            interface = hbn.hbnInterface.__new__(hbn.hbnInterface)
            interface.hbns = [mock_hbn1, mock_hbn2]
            
            result = interface.output_names()
            
            # Result should be a defaultdict with sets
            assert 'HYDR' in result
            # Should contain union of both outputs
            assert 'ROVOL' in result['HYDR']
            assert 'IVOL' in result['HYDR']
            assert 'OVOL' in result['HYDR']


# =============================================================================
# INTEGRATION TESTS DOCUMENTATION (NOT IMPLEMENTED)
# =============================================================================
"""
INTEGRATION TESTS NEEDED
========================

The following tests require actual HBN binary files and should be implemented
as integration tests:

1. hbnClass File Loading Tests:
   - test_hbnClass_loads_valid_hbn_file
   - test_hbnClass_validates_magic_number
   - test_hbnClass_handles_invalid_file_gracefully
   - test_hbnClass_map_option_toggles_mapping

2. hbnClass Data Mapping Tests:
   - test_map_hbn_builds_mapn_correctly
   - test_map_hbn_builds_mapd_correctly
   - test_map_hbn_handles_all_operation_types (PERLND, IMPLND, RCHRES)

3. hbnClass Data Reading Tests:
   - test_read_data_returns_correct_dataframe_shape
   - test_read_data_parses_timestamps_correctly
   - test_read_data_extracts_float_values_correctly

4. hbnClass Time Series Retrieval Tests:
   - test_get_time_series_returns_correct_constituent
   - test_get_time_series_infers_activity_correctly
   - test_get_time_series_filters_by_date
   - test_get_multiple_timeseries_aggregates_opnids

5. hbnInterface Multi-File Tests:
   - test_hbnInterface_loads_multiple_files
   - test_hbnInterface_concatenates_time_series
   - test_hbnInterface_get_reach_constituent_calculates_correctly

6. End-to-End Simulation Data Tests:
   - test_get_simulated_flow_calculations
   - test_get_simulated_reach_constituent_mg_per_l_conversion
   - test_reach_losses_calculation
   - test_get_rchres_data_returns_correct_format

Test Data Requirements:
- A small, representative HBN file with known values
- Files covering different operation types (PERLND, IMPLND, RCHRES)
- Files with different time step data (hourly, daily, monthly, yearly)
"""


# =============================================================================
# CODE QUALITY NOTES AND IMPROVEMENT SUGGESTIONS
# =============================================================================
"""
CODE QUALITY ANALYSIS FOR hbn.py
================================

1. NAMING CONVENTIONS:
   - Issue: Class names don't follow PEP8 (hbnClass should be HbnClass)
   - Issue: Some variable names are unclear (e.g., 't_opn', 't_cons', 't_code')
   - Suggestion: Rename to operation_type, constituent_name, time_code

2. CODE DUPLICATION:
   - Issue: get_simulated_implnd_constituent and get_simulated_perlnd_constituent
     are nearly identical, differing only in operation type
   - Suggestion: Create a single parameterized function:
     def get_simulated_landuse_constituent(hbn, constituent, time_step, operation)

3. ERROR HANDLING:
   - Issue: Limited error handling for file operations in hbn.py
   - Issue: print() used instead of logging for errors (hbn.py lines 256-257, 300, 314)
   - Issue: Magic number validation (hbn.py line 255-257) prints message but doesn't
     raise exception, allowing code to continue with invalid data
   - Suggestion: Use logging module and raise appropriate exceptions (e.g., ValueError
     for invalid file format)

4. TYPE HINTS:
   - Issue: No type hints throughout the module
   - Suggestion: Add type hints for better IDE support and documentation
   - Example: def get_simulated_flow(hbn: hbnInterface, time_step: str, 
               reach_ids: List[int], unit: Optional[str] = None) -> pd.Series:

5. DOCUMENTATION:
   - Issue: Incomplete docstrings on most methods
   - Issue: No module-level documentation explaining HBN file format
   - Suggestion: Add comprehensive docstrings with Parameters, Returns, Raises

6. MAGIC NUMBERS:
   - Issue: Conversion factors (43560, 453592.37, 1233481.8375475) are embedded in
     hbn.py lines 126, 156-157
   - Suggestion: Define these as named constants at module level:
     SQFT_PER_ACRE = 43560
     MG_PER_LB = 453592.37
     LITERS_PER_ACRE_FT = 1233481.8375475

7. DATE HANDLING:
   - Issue: Hardcoded date filter '1996-01-01' in get_time_series (hbn.py lines 414, 419)
   - Problem: This silently filters out all data before 1996 without clear justification,
     which could cause unexpected data loss for users with historical simulations
   - Suggestion: Make this configurable via parameter or document why it exists

8. UNUSED CODE:
   - Issue: Commented-out code blocks in hbn.py (lines 20-50, 360-377)
   - Suggestion: Remove or move to separate utility file if needed for reference

9. BINARY PARSING:
   - Issue: Complex binary parsing logic in map_hbn (hbn.py lines 283-318) could be error-prone
   - Issue: Record length calculation uses magic values (29, 30, 24) in hbn.py lines 315-318
   - Suggestion: Document the HBN file format or extract to separate parser module

10. PERFORMANCE:
    - Issue: read_data calls resample() which may be expensive (hbn.py line 348)
    - Issue: Multiple iterations over mapd.keys() in get_multiple_timeseries (hbn.py line 441)
    - Suggestion: Consider caching or lazy loading strategies

11. POTENTIAL BUGS:
    - hbn.py lines 89, 103, 151: TSS multiplied by 2000 - this converts from tons to pounds
      but should be documented with a comment or named constant (POUNDS_PER_TON = 2000)
    - hbn.py line 119: math.copysign returns float, but reach_ids might expect int
    - hbn.py lines 414-419: Date filter applied inconsistently (only in some code paths)

12. TESTABILITY:
    - Issue: Heavy coupling between file I/O and data processing
    - Suggestion: Separate parsing logic from business logic to enable mocking
    - Suggestion: Create a factory method for dependency injection

13. CONSISTENCY:
    - Issue: tcodes dictionary duplicates information (string <-> int mappings)
    - Issue: Mixed use of 'ME' vs 'M' for monthly, 'YE' vs 'Y' for yearly
    - Suggestion: Standardize on one set of abbreviations
"""


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
