"""Regression test for the report's "additive-only" non-negotiable
(Chapter 1 / 3.2): the pre-existing ingestion, scoring, and alert/digest
pipeline must be provably unchanged by everything added this semester --
with one deliberate, documented exception: the scoring formula itself.

Bounded dynamic weighting (signals/scorer.py, compute_dynamic_weights) was
added intentionally after this non-negotiable was written, specifically to
make the score defensible ("why does this weight matter") rather than a
fixed, unexplained constant. The base weights (30/40/30) are UNCHANGED --
only the swing around them is new. test_dynamic_weights.py covers the new
mechanism's rules directly; this file's golden value is recomputed by hand
below (not just re-pinned to whatever the new code outputs) so it still
catches unintended drift.
"""

from signals.models import MaterialSignal
from signals.scorer import PRICE_WEIGHT, TRADE_WEIGHT, EXPORT_WEIGHT, disruption_score


def test_disruption_score_base_weights_unchanged():
    """The base weights are the documented floor/baseline -- dynamic
    weighting bounds its swing around these, it doesn't replace them."""
    assert (PRICE_WEIGHT, EXPORT_WEIGHT, TRADE_WEIGHT) == (0.30, 0.40, 0.30)


def test_disruption_score_exact_value_for_fixed_input():
    signals = [
        MaterialSignal(material="Lithium", source="usgs", price_delta=20),
        MaterialSignal(material="Lithium", source="sanctions", export_mentions=2),
        MaterialSignal(material="Lithium", source="comtrade", trade_hhi=5000),
    ]
    score, factors = disruption_score(signals)
    # factors are unchanged from the original scorer (price=6, export=13,
    # trade=16 -- see the averaging math in disruption_score). trade is
    # highest, so it's dominant: price loses 30%*0.30=0.09 -> 0.21, export
    # loses 30%*0.40=0.12 -> 0.28, trade gains both -> 0.30+0.09+0.12=0.51.
    # score = int(6*0.21 + 13*0.28 + 16*0.51) = int(1.26+3.64+8.16) = 13.
    assert (score, factors) == (13, {"price": 6, "export": 13, "trade": 16})


def test_scheduler_public_surface_unchanged():
    """The existing threshold-alert/digest pipeline's public functions must
    still exist with the same names after the new snapshot job is
    registered in build_scheduler()."""
    from scheduler import jobs as scheduler_jobs

    assert callable(scheduler_jobs.run_pipeline)
    assert callable(scheduler_jobs.run_pipeline_once)
    assert callable(scheduler_jobs.generate_digest)
    assert callable(scheduler_jobs.build_scheduler)
