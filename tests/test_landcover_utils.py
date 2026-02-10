"""Tests for the landcover_utils module."""
from hspf.landcover_utils import (
    LANDCOVER_DF,
    get_landcover,
    get_agricultural_perlnds,
    get_forested_perlnds,
    get_cropland_perlnds,
    get_perlnds_by_landcover,
    filter_perlnds_by_landcover,
    get_all_models,
    get_model_perlnds,
    get_landcover_summary,
    get_landcovers_for_perlnds,
    get_cross_model_summary,
    get_all_landcover_types,
    get_perlnds_by_column_value,
)


def test_global_dataframe_loaded():
    """Test that LANDCOVER_DF is loaded as a global DataFrame."""
    assert LANDCOVER_DF is not None
    assert len(LANDCOVER_DF) > 0


def test_get_landcover_returns_dict():
    """Test that get_landcover returns a dictionary for valid inputs."""
    result = get_landcover('BigFork', 10)
    assert isinstance(result, dict)
    assert result['model'] == 'BigFork'
    assert result['OPNID'] == 10.0
    assert result['Landcover'] == 'Wetland'


def test_get_landcover_returns_none_for_invalid_input():
    """Test that get_landcover returns None for invalid inputs."""
    result = get_landcover('NonExistent', 999)
    assert result is None


def test_get_landcover_forest():
    """Test getting a forest landcover."""
    result = get_landcover('BigFork', 12)
    assert result is not None
    assert result['Landcover'] == 'Forest'
    assert result['Forest Species'] == 'Deciduous'
    assert result['Forest Age'] == 'Old'


def test_get_agricultural_perlnds():
    """Test getting agricultural perlnds for a model."""
    result = get_agricultural_perlnds('BigFork')
    assert isinstance(result, list)
    assert 18 in result


def test_get_agricultural_perlnds_bigsioux():
    """Test getting agricultural perlnds for BigSioux model."""
    result = get_agricultural_perlnds('BigSioux')
    assert isinstance(result, list)
    assert set(result) == {14, 15, 16}


def test_get_forested_perlnds():
    """Test getting forested perlnds for a model."""
    result = get_forested_perlnds('BigFork')
    assert isinstance(result, list)
    assert set(result) == {12, 13, 14, 15, 16, 17}


def test_get_forested_perlnds_empty_for_no_forests():
    """Test getting forested perlnds returns empty for model with no forests."""
    result = get_forested_perlnds('NonExistent')
    assert result == []


def test_get_cropland_perlnds():
    """Test getting cropland perlnds for a model."""
    result = get_cropland_perlnds('BigSioux')
    assert isinstance(result, list)
    assert set(result) == {14, 15, 16}


def test_get_cropland_perlnds_empty():
    """Test getting cropland perlnds returns empty for model with no croplands."""
    result = get_cropland_perlnds('BigFork')
    assert result == []


def test_perlnd_ids_are_integers():
    """Test that all returned perlnd IDs are integers."""
    agricultural = get_agricultural_perlnds('BigSioux')
    forested = get_forested_perlnds('BigFork')
    cropland = get_cropland_perlnds('BigSioux')
    
    for perlnd_id in agricultural + forested + cropland:
        assert isinstance(perlnd_id, int)


def test_get_perlnds_by_landcover():
    """Test getting perlnds by a specific landcover type."""
    result = get_perlnds_by_landcover('BigFork', 'Wetland')
    assert isinstance(result, list)
    assert 10 in result


def test_filter_perlnds_by_landcover():
    """Test filtering a list of perlnds by landcover type."""
    perlnd_ids = [12, 13, 14, 15, 18, 20]
    result = filter_perlnds_by_landcover('BigFork', perlnd_ids, 'Forest')
    assert set(result) == {12, 13, 14, 15}


def test_get_all_models():
    """Test getting all model names."""
    result = get_all_models()
    assert isinstance(result, list)
    assert 'BigFork' in result
    assert 'BigSioux' in result


def test_get_model_perlnds():
    """Test getting all perlnds for a model."""
    result = get_model_perlnds('BigFork')
    assert isinstance(result, list)
    assert len(result) > 0


def test_get_landcover_summary():
    """Test getting landcover summary for a model."""
    result = get_landcover_summary('BigFork')
    assert isinstance(result, dict)
    assert 'Forest' in result
    assert result['Forest'] > 0


def test_get_landcovers_for_perlnds():
    """Test getting landcover info for a list of perlnd IDs."""
    result = get_landcovers_for_perlnds('BigFork', [10, 12])
    assert isinstance(result, list)
    assert len(result) == 2


def test_get_cross_model_summary():
    """Test getting cross-model summary for a landcover type."""
    result = get_cross_model_summary('Forest')
    assert isinstance(result, dict)
    assert 'BigFork' in result


def test_get_all_landcover_types():
    """Test getting all landcover types."""
    result = get_all_landcover_types()
    assert isinstance(result, list)
    assert 'Forest' in result
    assert 'Agricultural' in result


def test_get_perlnds_by_column_value():
    """Test getting perlnds by column value."""
    result = get_perlnds_by_column_value('BigFork', 'Forest Species', 'Deciduous')
    assert isinstance(result, list)
    assert 12 in result


def test_get_perlnds_by_column_value_invalid_column():
    """Test that invalid column returns empty list."""
    result = get_perlnds_by_column_value('BigFork', 'NonExistentColumn', 'Value')
    assert result == []
