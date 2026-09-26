from signals.models import MaterialSignal

# Base weights -- unchanged from the original, documented methodology.
# Dynamic weighting (below) starts from exactly these and bounds its swing
# around them, rather than replacing them, so the original fixed-weight
# case remains a valid, defensible baseline.
PRICE_WEIGHT = 0.30
EXPORT_WEIGHT = 0.40
TRADE_WEIGHT = 0.30
BASE_WEIGHTS = {"price": PRICE_WEIGHT, "export": EXPORT_WEIGHT, "trade": TRADE_WEIGHT}

# Fraction of each NON-dominant factor's base weight transferred to
# whichever factor is currently strongest. Fixed at 30% deliberately: since
# every factor's floor is implicitly half its base weight, a 30% cut can
# never breach it (30% < 50%), so no factor can ever be silenced.
DOMINANCE_TRANSFER_FRACTION = 0.30


def compute_dynamic_weights(price: int, export: int, trade: int) -> dict[str, float]:
    """Bounded dominance-transfer weighting.

    Starts from the same fixed base weights the report documents, then
    moves a fixed fraction of each OTHER factor's base weight onto whichever
    real signal (price momentum, export-restriction mentions, trade
    concentration) is currently strongest for this material. Deterministic
    and always sums to 1.0. Ties go to price, then export, then trade (the
    fixed iteration order below), so the result is always reproducible.
    """
    values = {"price": price, "export": export, "trade": trade}
    dominant = max(values, key=values.get)

    weights = dict(BASE_WEIGHTS)
    for factor in weights:
        if factor != dominant:
            transfer = DOMINANCE_TRANSFER_FRACTION * BASE_WEIGHTS[factor]
            weights[factor] -= transfer
            weights[dominant] += transfer
    return weights


def disruption_score(signals: list[MaterialSignal]) -> tuple[int, dict]:
    """Pure scoring function with no side effects.

    Three real factors, each normalized to 0-100:
    - price delta (trailing price momentum)
    - export restriction mentions (real news-scan signal)
    - trade concentration (real, static HHI)

    Combined with dynamic, bounded weights (compute_dynamic_weights): the
    currently-strongest factor is boosted, but every factor always keeps at
    least half of its original base weight (30/40/30).
    """
    if not signals:
        return 0, {"price": 0, "export": 0, "trade": 0}

    price = min(100, max(0, int(sum(max(0, s.price_delta) for s in signals) / len(signals))))
    export = min(100, max(0, int(sum(min(100, s.export_mentions * 20) for s in signals) / len(signals))))
    trade = min(100, max(0, int(sum(min(100, s.trade_hhi / 100) for s in signals) / len(signals))))

    weights = compute_dynamic_weights(price, export, trade)
    score = int(price * weights["price"] + export * weights["export"] + trade * weights["trade"])
    return score, {"price": price, "export": export, "trade": trade}


class DisruptionScorer:
    @staticmethod
    def score(signals: list[MaterialSignal]) -> tuple[int, dict]:
        return disruption_score(signals)
