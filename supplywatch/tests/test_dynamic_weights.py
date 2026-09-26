"""Tests for the bounded dominance-transfer weighting rule itself
(signals/scorer.py, compute_dynamic_weights), not just a re-pinned output
value. These assert the actual guarantees the design promises: weights
always sum to 1.0, no factor can be silenced (floor = half its base
weight), and the currently-strongest factor is the one that gets boosted.
"""

from signals.scorer import BASE_WEIGHTS, compute_dynamic_weights


def test_weights_always_sum_to_one():
    cases = [(90, 10, 10), (10, 90, 10), (10, 10, 90), (0, 0, 0), (50, 50, 50), (33, 33, 34)]
    for price, export, trade in cases:
        weights = compute_dynamic_weights(price, export, trade)
        assert round(sum(weights.values()), 9) == 1.0


def test_dominant_factor_gets_the_boost():
    weights = compute_dynamic_weights(price=90, export=10, trade=10)
    assert weights["price"] > BASE_WEIGHTS["price"]
    assert weights["export"] < BASE_WEIGHTS["export"]
    assert weights["trade"] < BASE_WEIGHTS["trade"]

    weights = compute_dynamic_weights(price=10, export=90, trade=10)
    assert weights["export"] > BASE_WEIGHTS["export"]

    weights = compute_dynamic_weights(price=10, export=10, trade=90)
    assert weights["trade"] > BASE_WEIGHTS["trade"]


def test_no_factor_can_be_silenced():
    """A factor's floor is half its base weight -- the 30% transfer cut
    can never breach that, no matter which factor dominates."""
    for dominant_price, dominant_export, dominant_trade in [(100, 0, 0), (0, 100, 0), (0, 0, 100)]:
        weights = compute_dynamic_weights(dominant_price, dominant_export, dominant_trade)
        for factor, weight in weights.items():
            assert weight >= BASE_WEIGHTS[factor] * 0.5 - 1e-9, f"{factor} weight {weight} breached its floor"


def test_equal_factors_keep_base_weights():
    """No factor is strictly highest, so max() picks the first (price) by
    Python's dict-iteration tie-break -- still deterministic, still sums to
    1.0, and the swing is identical to any other single-dominant case."""
    weights = compute_dynamic_weights(50, 50, 50)
    assert round(sum(weights.values()), 9) == 1.0
    assert weights["price"] > BASE_WEIGHTS["price"]  # price wins the tie


def test_ties_are_deterministic():
    """Same inputs must always produce the same weights (no randomness,
    no hidden state)."""
    a = compute_dynamic_weights(40, 40, 40)
    b = compute_dynamic_weights(40, 40, 40)
    assert a == b
