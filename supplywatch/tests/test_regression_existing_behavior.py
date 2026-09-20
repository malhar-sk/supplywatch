"""Regression test for the report's "additive-only" non-negotiable
(Chapter 1 / 3.2): the pre-existing ingestion, scoring, and alert/digest
pipeline must be provably unchanged by everything added this semester.

test_scorer.py already checks disruption_score()'s output is *within
range*; this test pins its *exact* value for a fixed input, so a future
change to the weighting constants or formula — even one that still
produces a "valid" score — gets caught here instead of silently drifting.
"""

from signals.models import MaterialSignal
from signals.scorer import PRICE_WEIGHT, TRADE_WEIGHT, EXPORT_WEIGHT, disruption_score


def test_disruption_score_weights_unchanged():
    assert (PRICE_WEIGHT, EXPORT_WEIGHT, TRADE_WEIGHT) == (0.30, 0.40, 0.30)


def test_disruption_score_exact_value_for_fixed_input():
    signals = [
        MaterialSignal(material="Lithium", source="usgs", price_delta=20),
        MaterialSignal(material="Lithium", source="sanctions", export_mentions=2),
        MaterialSignal(material="Lithium", source="comtrade", trade_hhi=5000),
    ]
    score, factors = disruption_score(signals)
    # Golden values as of the pre-existing (unmodified) scorer. If this
    # assertion ever fails, the scoring formula itself changed — which
    # this semester's build is explicitly not supposed to do.
    assert (score, factors) == (11, {"price": 6, "export": 13, "trade": 16})


def test_scheduler_public_surface_unchanged():
    """The existing threshold-alert/digest pipeline's public functions must
    still exist with the same names after the new snapshot job is
    registered in build_scheduler()."""
    from scheduler import jobs as scheduler_jobs

    assert callable(scheduler_jobs.run_pipeline)
    assert callable(scheduler_jobs.run_pipeline_once)
    assert callable(scheduler_jobs.generate_digest)
    assert callable(scheduler_jobs.build_scheduler)
