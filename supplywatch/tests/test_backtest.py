"""Backtest event-intensity methodology test (Chapter 6.1): the documented-
event proxy must actually respond at the real, cited dates -- otherwise the
backtest chart would just be decoration."""

from datetime import date

from snapshot.backtest import EVENTS, export_intensity


def test_indium_jumps_after_its_licensing_date():
    before = export_intensity("Indium", EVENTS[0].date - __import__("datetime").timedelta(days=1))
    after = export_intensity("Indium", EVENTS[0].date)
    assert after > before


def test_heavy_ree_peaks_during_suspended_second_wave_window():
    baseline = export_intensity("Dysprosium", date(2025, 3, 1))
    after_heavy_ree = export_intensity("Dysprosium", EVENTS[1].date)
    during_second_wave = export_intensity("Dysprosium", date(2025, 10, 15))
    after_suspension = export_intensity("Dysprosium", EVENTS[3].date)

    assert after_heavy_ree > baseline
    assert during_second_wave > after_heavy_ree  # the peak
    assert after_suspension < during_second_wave  # eases, but...
    assert after_suspension >= after_heavy_ree  # ...doesn't fall below the Apr 2025 baseline


def test_pre_controlled_materials_are_constant_not_spiked():
    # Gallium/Germanium controls predate this backtest window (Aug 2023 /
    # Dec 2024) -- a flat elevated line is the accurate representation,
    # not an artificial mid-window spike.
    early = export_intensity("Gallium", date(2025, 1, 6))
    late = export_intensity("Gallium", date(2026, 8, 1))
    assert early == late


def test_out_of_scope_materials_stay_at_low_baseline():
    # Cobalt/Lithium/Graphite aren't targeted by this specific Chinese
    # rare-earth regime; their own risk drivers are out of scope for this
    # particular backtest.
    for material in ("Cobalt", "Lithium", "Graphite"):
        assert export_intensity(material, EVENTS[2].date) == export_intensity(material, date(2025, 1, 6))
