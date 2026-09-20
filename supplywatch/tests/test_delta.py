"""Delta/trend test (Chapter 3.2 contract): hand-constructed score
sequences with a known expected trend direction. Pure function, no DB.
"""

from snapshot.delta import TREND_FALLING, TREND_RISING, TREND_UNCHANGED, compute_trend


def test_rising_sequence():
    assert compute_trend([40, 55]) == TREND_RISING
    assert compute_trend([10, 20, 30, 45]) == TREND_RISING


def test_falling_sequence():
    assert compute_trend([55, 40]) == TREND_FALLING
    assert compute_trend([80, 60, 45, 30]) == TREND_FALLING


def test_unchanged_sequence():
    assert compute_trend([40, 40]) == TREND_UNCHANGED
    assert compute_trend([25, 25, 25]) == TREND_UNCHANGED


def test_insufficient_history_is_unchanged():
    assert compute_trend([]) == TREND_UNCHANGED
    assert compute_trend([50]) == TREND_UNCHANGED
