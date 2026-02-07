# -*- coding: utf-8 -*-
"""
Tests for the OutputWriter class.
"""
import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestOutputWriter:
    """Tests for the OutputWriter class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create mock hbns interface
        self.mock_hbns = MagicMock()
        self.mock_uci = MagicMock()
        self.mock_wdms = MagicMock()
        
        # Set up return values for hbns methods
        self.mock_df = pd.DataFrame(
            {'90': [100.0, 110.0, 105.0]},
            index=pd.date_range('2020-01-01', periods=3, freq='D')
        )
        self.mock_df.attrs = {'unit': 'cfs', 'constituent': 'Q', 'reach_ids': [90]}
        
        self.mock_hbns.get_reach_constituent.return_value = self.mock_df
        self.mock_hbns.get_perlnd_constituent.return_value = self.mock_df
        self.mock_hbns.get_implnd_constituent.return_value = self.mock_df
        self.mock_hbns.output_names.return_value = {
            'HYDR': {'ROVOL', 'IVOL'},
            'SEDTRN': {'ROSEDTOT', 'ISEDTOT'}
        }
    
    def test_import(self):
        """Test that OutputWriter can be imported."""
        from hspf.output import OutputWriter
        assert OutputWriter is not None
    
    def test_init(self):
        """Test OutputWriter initialization."""
        from hspf.output import OutputWriter
        
        writer = OutputWriter(self.mock_hbns, self.mock_uci, self.mock_wdms)
        
        assert writer.hbns == self.mock_hbns
        assert writer.uci == self.mock_uci
        assert writer.wdms == self.mock_wdms
    
    def test_normalize_time_step(self):
        """Test time step normalization."""
        from hspf.output import OutputWriter
        
        writer = OutputWriter(self.mock_hbns)
        
        assert writer._normalize_time_step('hourly') == 'h'
        assert writer._normalize_time_step('daily') == 'D'
        assert writer._normalize_time_step('monthly') == 'ME'
        assert writer._normalize_time_step('yearly') == 'YE'
        assert writer._normalize_time_step(2) == 'h'
        assert writer._normalize_time_step(3) == 'D'
        assert writer._normalize_time_step(4) == 'ME'
        assert writer._normalize_time_step(5) == 'YE'
    
    def test_normalize_reach_ids_int(self):
        """Test reach_ids normalization with int input."""
        from hspf.output import OutputWriter
        
        writer = OutputWriter(self.mock_hbns)
        
        result = writer._normalize_reach_ids(90)
        assert result == [90]
    
    def test_normalize_reach_ids_list(self):
        """Test reach_ids normalization with list input."""
        from hspf.output import OutputWriter
        
        writer = OutputWriter(self.mock_hbns)
        
        result = writer._normalize_reach_ids([10, 50, 90])
        assert result == [10, 50, 90]
    
    def test_get_reach_output(self):
        """Test getting reach output."""
        from hspf.output import OutputWriter
        
        writer = OutputWriter(self.mock_hbns, self.mock_uci)
        
        result = writer.get_reach_output(
            reach_ids=[90],
            constituent='Q',
            time_step='daily'
        )
        
        self.mock_hbns.get_reach_constituent.assert_called_once_with(
            constituent='Q',
            reach_ids=[90],
            time_step='D',
            unit=None
        )
        assert result is not None
    
    def test_get_reach_output_with_unit(self):
        """Test getting reach output with specified unit."""
        from hspf.output import OutputWriter
        
        writer = OutputWriter(self.mock_hbns, self.mock_uci)
        
        writer.get_reach_output(
            reach_ids=[90],
            constituent='Q',
            time_step='daily',
            unit='acrft'
        )
        
        self.mock_hbns.get_reach_constituent.assert_called_with(
            constituent='Q',
            reach_ids=[90],
            time_step='D',
            unit='acrft'
        )
    
    def test_get_perlnd_output(self):
        """Test getting PERLND output."""
        from hspf.output import OutputWriter
        
        writer = OutputWriter(self.mock_hbns, self.mock_uci)
        
        writer.get_perlnd_output(constituent='TSS', time_step='yearly')
        
        self.mock_hbns.get_perlnd_constituent.assert_called_once()
    
    def test_get_implnd_output(self):
        """Test getting IMPLND output."""
        from hspf.output import OutputWriter
        
        writer = OutputWriter(self.mock_hbns, self.mock_uci)
        
        writer.get_implnd_output(constituent='TSS', time_step='yearly')
        
        self.mock_hbns.get_implnd_constituent.assert_called_once()
    
    def test_write_reach_output_csv(self, tmp_path):
        """Test writing reach output to CSV."""
        from hspf.output import OutputWriter
        
        writer = OutputWriter(self.mock_hbns, self.mock_uci)
        
        output_file = tmp_path / "output.csv"
        result = writer.write_reach_output(
            filepath=output_file,
            reach_ids=[90],
            constituent='Q',
            time_step='daily',
            format='csv'
        )
        
        assert result == output_file
        assert output_file.exists()
    
    def test_write_reach_output_excel(self, tmp_path):
        """Test writing reach output to Excel."""
        from hspf.output import OutputWriter
        
        writer = OutputWriter(self.mock_hbns, self.mock_uci)
        
        output_file = tmp_path / "output.xlsx"
        result = writer.write_reach_output(
            filepath=output_file,
            reach_ids=[90],
            constituent='Q',
            time_step='daily',
            format='excel'
        )
        
        assert result == output_file
        assert output_file.exists()
    
    def test_write_reach_output_invalid_format(self, tmp_path):
        """Test writing reach output with invalid format raises error."""
        from hspf.output import OutputWriter
        
        writer = OutputWriter(self.mock_hbns, self.mock_uci)
        
        output_file = tmp_path / "output.txt"
        
        with pytest.raises(ValueError, match="Unsupported format"):
            writer.write_reach_output(
                filepath=output_file,
                reach_ids=[90],
                constituent='Q',
                time_step='daily',
                format='invalid'
            )
    
    def test_get_summary(self):
        """Test getting summary report."""
        from hspf.output import OutputWriter
        
        writer = OutputWriter(self.mock_hbns, self.mock_uci)
        
        result = writer.get_summary(
            reach_ids=[90],
            constituents=['Q']
        )
        
        assert isinstance(result, pd.DataFrame)
    
    def test_get_monthly_summary(self):
        """Test getting monthly summary."""
        from hspf.output import OutputWriter
        
        # Create mock with monthly index
        monthly_df = pd.DataFrame(
            {'90': [100.0, 110.0, 105.0]},
            index=pd.date_range('2020-01-01', periods=3, freq='ME')
        )
        self.mock_hbns.get_reach_constituent.return_value = monthly_df
        
        writer = OutputWriter(self.mock_hbns, self.mock_uci)
        
        result = writer.get_monthly_summary(
            reach_ids=[90],
            constituent='Q'
        )
        
        assert isinstance(result, pd.DataFrame)
    
    def test_available_constituents(self):
        """Test getting available constituents."""
        from hspf.output import OutputWriter
        
        writer = OutputWriter(self.mock_hbns, self.mock_uci)
        
        result = writer.available_constituents()
        
        self.mock_hbns.output_names.assert_called_once()
        assert 'HYDR' in result
        assert 'SEDTRN' in result


class TestOutputWriterFromHspfModel:
    """Test OutputWriter integration with hspfModel."""
    
    def test_output_attribute_exists(self):
        """Test that hspfModel creates output attribute with OutputWriter."""
        from pathlib import Path
        
        # Read the hspfModel.py source file directly
        hspf_model_path = Path(__file__).parent.parent / 'src' / 'hspf' / 'hspfModel.py'
        source = hspf_model_path.read_text()
        
        # Check that OutputWriter is imported in the module
        assert 'from .output import OutputWriter' in source, \
            "OutputWriter should be imported in hspfModel module"
        
        # Check that output attribute is created in __init__
        assert 'self.output = OutputWriter' in source, \
            "hspfModel.__init__ should create self.output = OutputWriter(...)"
