"""Tests for the landcover_utils module."""
from hspf.landcover_utils import (
    get_landcover,
    get_agricultural_perlnds,
    get_forested_perlnds,
    get_cropland_perlnds,
)


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
