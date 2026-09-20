"""Price fallback chain ordering (Part 1, Pareto items #2 and #4): each
fallback must only fire when the previous one returned no usable data
(None), never when it returned a genuine 0.0% change."""

from unittest.mock import patch

from ingest.usgs import _fetch_price_delta_sync


def test_yfinance_result_used_when_available():
    with patch("ingest.usgs._fetch_price_delta_yfinance", return_value=5.0), \
         patch("ingest.usgs._fetch_price_delta_twelvedata") as td, \
         patch("ingest.usgs._fetch_price_delta_finnhub") as fh:
        assert _fetch_price_delta_sync("Cobalt") == 5.0
        td.assert_not_called()
        fh.assert_not_called()


def test_genuine_zero_is_not_treated_as_a_failure():
    # A real 0.0% change must NOT trigger the fallback chain -- only a
    # missing result (None) should.
    with patch("ingest.usgs._fetch_price_delta_yfinance", return_value=0.0), \
         patch("ingest.usgs._fetch_price_delta_twelvedata") as td:
        assert _fetch_price_delta_sync("Cobalt") == 0.0
        td.assert_not_called()


def test_falls_through_to_twelvedata_when_yfinance_has_nothing():
    with patch("ingest.usgs._fetch_price_delta_yfinance", return_value=None), \
         patch("ingest.usgs._fetch_price_delta_twelvedata", return_value=3.2) as td, \
         patch("ingest.usgs._fetch_price_delta_finnhub") as fh:
        assert _fetch_price_delta_sync("Indium") == 3.2
        td.assert_called_once()
        fh.assert_not_called()


def test_falls_through_to_finnhub_when_first_two_have_nothing():
    with patch("ingest.usgs._fetch_price_delta_yfinance", return_value=None), \
         patch("ingest.usgs._fetch_price_delta_twelvedata", return_value=None), \
         patch("ingest.usgs._fetch_price_delta_finnhub", return_value=-1.4) as fh:
        assert _fetch_price_delta_sync("Indium") == -1.4
        fh.assert_called_once()


def test_neutral_zero_when_every_source_has_nothing():
    with patch("ingest.usgs._fetch_price_delta_yfinance", return_value=None), \
         patch("ingest.usgs._fetch_price_delta_twelvedata", return_value=None), \
         patch("ingest.usgs._fetch_price_delta_finnhub", return_value=None):
        assert _fetch_price_delta_sync("Indium") == 0.0


def test_twelvedata_and_finnhub_are_noops_without_api_keys():
    from ingest.usgs import _fetch_price_delta_finnhub, _fetch_price_delta_twelvedata

    with patch("ingest.usgs.get_settings") as mock_settings:
        mock_settings.return_value.twelvedata_api_key = ""
        mock_settings.return_value.finnhub_api_key = ""
        assert _fetch_price_delta_twelvedata("Cobalt") is None
        assert _fetch_price_delta_finnhub("Cobalt") is None
