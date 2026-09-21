"""Residual helpers kept for compatibility during the core split."""

from hspf.core.constituents import get_tcons, nutrient_id, nutrient_name
from hspf.core.conventions import decompose_perlands


def get_months(month):
    months = {
        1: "JAN",
        2: "FEB",
        3: "MAR",
        4: "APR",
        5: "MAY",
        6: "JUN",
        7: "JUL",
        8: "AUG",
        9: "SEP",
        10: "OCT",
        11: "NOV",
        12: "DEC",
    }
    return months[month]


def get_adjacent_month(month, side=1):
    months = {
        1: [12, 2],
        2: [1, 3],
        3: [2, 4],
        4: [3, 5],
        5: [4, 6],
        6: [5, 7],
        7: [6, 8],
        8: [7, 9],
        9: [8, 10],
        10: [9, 11],
        11: [10, 12],
        12: [11, 1],
    }
    return months[month][side]


__all__ = [
    "decompose_perlands",
    "get_adjacent_month",
    "get_months",
    "get_tcons",
    "nutrient_id",
    "nutrient_name",
]
