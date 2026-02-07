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


class TestReportWriter:
    """Tests for the ReportWriter class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create mock reports object
        self.mock_reports = MagicMock()
        
        # Set up return values for reports methods
        self.mock_df = pd.DataFrame(
            {'TVOLNO': [10, 20, 30], 'nonpoint': [100, 200, 300], 'ratio': [0.5, 0.6, 0.7]},
        )
        
        self.mock_reports.scour.return_value = self.mock_df
        self.mock_reports.landcover_area.return_value = self.mock_df
        self.mock_reports.annual_water_budget.return_value = self.mock_df
        self.mock_reports.annual_sediment_budget.return_value = self.mock_df
        self.mock_reports.ann_avg_subwatershed_loading.return_value = self.mock_df
        self.mock_reports.ann_avg_watershed_loading.return_value = self.mock_df
        self.mock_reports.ann_avg_yield.return_value = self.mock_df
        self.mock_reports.annual_precip.return_value = self.mock_df
        self.mock_reports.simulated_et.return_value = self.mock_df
    
    def test_import(self):
        """Test that ReportWriter can be imported."""
        from hspf.output import ReportWriter
        assert ReportWriter is not None
    
    def test_init(self):
        """Test ReportWriter initialization."""
        from hspf.output import ReportWriter
        
        writer = ReportWriter(self.mock_reports)
        
        assert writer.reports == self.mock_reports
    
    def test_get_scour_report(self):
        """Test getting scour report."""
        from hspf.output import ReportWriter
        
        writer = ReportWriter(self.mock_reports)
        result = writer.get_scour_report()
        
        self.mock_reports.scour.assert_called_once()
        assert isinstance(result, pd.DataFrame)
    
    def test_get_landcover_area(self):
        """Test getting landcover area."""
        from hspf.output import ReportWriter
        
        writer = ReportWriter(self.mock_reports)
        result = writer.get_landcover_area()
        
        self.mock_reports.landcover_area.assert_called_once()
        assert isinstance(result, pd.DataFrame)
    
    def test_get_water_budget(self):
        """Test getting water budget."""
        from hspf.output import ReportWriter
        
        writer = ReportWriter(self.mock_reports)
        result = writer.get_water_budget(operation='PERLND')
        
        self.mock_reports.annual_water_budget.assert_called_with('PERLND')
        assert isinstance(result, pd.DataFrame)
    
    def test_get_sediment_budget(self):
        """Test getting sediment budget."""
        from hspf.output import ReportWriter
        
        writer = ReportWriter(self.mock_reports)
        result = writer.get_sediment_budget()
        
        self.mock_reports.annual_sediment_budget.assert_called_once()
        assert isinstance(result, pd.DataFrame)
    
    def test_get_subwatershed_loading(self):
        """Test getting subwatershed loading."""
        from hspf.output import ReportWriter
        
        writer = ReportWriter(self.mock_reports)
        result = writer.get_subwatershed_loading(constituent='TSS')
        
        self.mock_reports.ann_avg_subwatershed_loading.assert_called_with('TSS')
        assert isinstance(result, pd.DataFrame)
    
    def test_get_watershed_loading(self):
        """Test getting watershed loading."""
        from hspf.output import ReportWriter
        
        writer = ReportWriter(self.mock_reports)
        result = writer.get_watershed_loading(constituent='TP', reach_ids=[90])
        
        self.mock_reports.ann_avg_watershed_loading.assert_called_with('TP', [90])
        assert isinstance(result, pd.DataFrame)
    
    def test_get_watershed_loading_with_int(self):
        """Test getting watershed loading with int reach_id."""
        from hspf.output import ReportWriter
        
        writer = ReportWriter(self.mock_reports)
        result = writer.get_watershed_loading(constituent='TP', reach_ids=90)
        
        self.mock_reports.ann_avg_watershed_loading.assert_called_with('TP', [90])
    
    def test_get_yield(self):
        """Test getting yield."""
        from hspf.output import ReportWriter
        
        writer = ReportWriter(self.mock_reports)
        result = writer.get_yield(constituent='Q', reach_ids=[90])
        
        self.mock_reports.ann_avg_yield.assert_called_with('Q', [90])
        assert isinstance(result, pd.DataFrame)
    
    def test_get_annual_precip(self):
        """Test getting annual precipitation."""
        from hspf.output import ReportWriter
        
        writer = ReportWriter(self.mock_reports)
        result = writer.get_annual_precip()
        
        self.mock_reports.annual_precip.assert_called_once()
        assert isinstance(result, pd.DataFrame)
    
    def test_get_simulated_et(self):
        """Test getting simulated ET."""
        from hspf.output import ReportWriter
        
        writer = ReportWriter(self.mock_reports)
        result = writer.get_simulated_et()
        
        self.mock_reports.simulated_et.assert_called_once()
        assert isinstance(result, pd.DataFrame)
    
    def test_write_scour_report_csv(self, tmp_path):
        """Test writing scour report to CSV."""
        from hspf.output import ReportWriter
        
        writer = ReportWriter(self.mock_reports)
        
        output_file = tmp_path / "scour.csv"
        result = writer.write_scour_report(filepath=output_file)
        
        assert result == output_file
        assert output_file.exists()
    
    def test_write_water_budget_excel(self, tmp_path):
        """Test writing water budget to Excel."""
        from hspf.output import ReportWriter
        
        writer = ReportWriter(self.mock_reports)
        
        output_file = tmp_path / "water_budget.xlsx"
        result = writer.write_water_budget(filepath=output_file, format='excel')
        
        assert result == output_file
        assert output_file.exists()
    
    def test_write_invalid_format(self, tmp_path):
        """Test writing with invalid format raises error."""
        from hspf.output import ReportWriter
        
        writer = ReportWriter(self.mock_reports)
        output_file = tmp_path / "output.txt"
        
        with pytest.raises(ValueError, match="Unsupported format"):
            writer.write_scour_report(filepath=output_file, format='invalid')
    
    def test_available_reports(self):
        """Test available_reports method."""
        from hspf.output import ReportWriter
        
        writer = ReportWriter(self.mock_reports)
        reports = writer.available_reports()
        
        assert 'scour_report' in reports
        assert 'water_budget' in reports
        assert 'sediment_budget' in reports
        assert 'subwatershed_loading' in reports
        assert 'watershed_loading' in reports
        assert 'yield' in reports


class TestReportWriterFromHspfModel:
    """Test ReportWriter integration with hspfModel."""
    
    def test_report_writer_attribute_exists(self):
        """Test that hspfModel creates report_writer attribute."""
        from pathlib import Path
        
        # Read the hspfModel.py source file directly
        hspf_model_path = Path(__file__).parent.parent / 'src' / 'hspf' / 'hspfModel.py'
        source = hspf_model_path.read_text()
        
        # Check that ReportWriter is imported in the module
        assert 'ReportWriter' in source, \
            "ReportWriter should be imported in hspfModel module"
        
        # Check that report_writer attribute is created in __init__
        assert 'self.report_writer = ReportWriter' in source, \
            "hspfModel.__init__ should create self.report_writer = ReportWriter(...)"
