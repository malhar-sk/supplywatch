# Delivery-policy eval: weekly score vs alert-only (band crossing)

**Scope.** Both views come from the same committed scores
(`backtest_output/backtest_results.csv`); only the delivery policy differs.
The backtest's export-control signal was derived from these same event dates,
so this does **not** show the score "detects" events. It compares two ways of
showing identical scores.

**Resolution.** 89 checkpoints, 2025-01-06 to 2026-09-14, spacing 7-day (weekly).
Leads are multiples of 7 days; they are not daily-precision results. Event dates
mostly fall between checkpoints, so "days after event" is to the next checkpoint.

**Definition.** baseline = median of the up-to-4 checkpoints strictly before
the event. Rise date = first checkpoint on/after the event, within
56 days (cut off at the next event on the same material), where the view's
value >= baseline + 10. Lead = alert-only rise date - brief rise date.
Alert-only value = score at the latest band crossing (bands 40/70).
Affected materials follow `export_intensity()`: Indium for event 1, Dysprosium and
Yttrium for events 2-6. Note: event 6 (EU entity ban) has no step in the backtest's
export signal (level already 4 from event 5), so it cannot move the score.

## Per event x material (11 pairs from 6 events)

| Event | Date | Material | Baseline | Brief rise (d after event) | Alert-only rise (d after event) | Lead (d) | Status |
|---|---|---|---|---|---|---|---|
| Indium licensing controls | 2025-02-04 | Indium | 28.0 | 6 | 6 | 0 | both_see |
| Heavy rare-earth export controls | 2025-04-04 | Dysprosium | 43.5 | 3 | - | >=53 (censored) | alert_never |
| Heavy rare-earth export controls | 2025-04-04 | Yttrium | 45.5 | 3 | - | >=53 (censored) | alert_never |
| Second-wave controls announced | 2025-10-09 | Dysprosium | 61.5 | 4 | 4 | 0 | both_see |
| Second-wave controls announced | 2025-10-09 | Yttrium | 64.0 | 4 | 4 | 0 | both_see |
| Second-wave controls suspended | 2025-11-07 | Dysprosium | 75.5 | - | - | - | no_rise |
| Second-wave controls suspended | 2025-11-07 | Yttrium | 76.5 | - | - | - | no_rise |
| US entity export ban | 2026-06-22 | Dysprosium | 60.0 | - | - | - | no_rise |
| US entity export ban | 2026-06-22 | Yttrium | 62.0 | - | - | - | no_rise |
| EU entity export ban | 2026-07-24 | Dysprosium | 65.0 | - | - | - | no_rise |
| EU entity export ban | 2026-07-24 | Yttrium | 68.0 | - | - | - | no_rise |

## Event rollup

| Event | Date | Pairs | both_see | alert_never | no_rise |
|---|---|---|---|---|---|
| Indium licensing controls | 2025-02-04 | 1 | 1 | 0 | 0 |
| Heavy rare-earth export controls | 2025-04-04 | 2 | 0 | 2 | 0 |
| Second-wave controls announced | 2025-10-09 | 2 | 2 | 0 | 0 |
| Second-wave controls suspended | 2025-11-07 | 2 | 0 | 0 | 2 |
| US entity export ban | 2026-06-22 | 2 | 0 | 0 | 2 |
| EU entity export ban | 2026-07-24 | 2 | 0 | 0 | 2 |

## Counts

- both_see: 3  (plain lead; mean lead = 0 days)
- alert_never (brief rises, alert-only view never updates; censored): 2
- no_rise (brief itself never rises >= 10): 6

Mean lead counting alert_never as the remaining window (a LOWER BOUND):
21.2 days over the 5 pairs with a rise.
Mean days from event to first visible rise (same pairs): brief
4 vs alert-only 25.2
(alert-only capped at the window where it never updates).

## Sensitivity to band boundaries

Cells: both_see/alert_never/no_rise ; mean lead lower bound (days)

| low/mod \ mod/elev | 60 | 65 | 70 | 75 | 80 |
|---|---|---|---|---|---|
| 30 | 3/2/6 ; 9.6d | 2/3/6 ; 26d | 3/2/6 ; 21.2d | 3/2/6 ; 21.2d | 3/2/6 ; 21.2d |
| 35 | 3/2/6 ; 9.6d | 2/3/6 ; 26d | 3/2/6 ; 21.2d | 3/2/6 ; 21.2d | 3/2/6 ; 21.2d |
| 40 | 3/2/6 ; 9.6d | 2/3/6 ; 26d | 3/2/6 ; 21.2d | 3/2/6 ; 21.2d | 3/2/6 ; 21.2d |
| 45 | 3/2/6 ; 9.6d | 3/2/6 ; 15.4d | 4/1/6 ; 10.6d | 4/1/6 ; 10.6d | 4/1/6 ; 10.6d |
| 50 | 2/3/6 ; 19.6d | 3/2/6 ; 14.8d | 4/1/6 ; 10d | 4/1/6 ; 10d | 4/1/6 ; 10d |

## Sensitivity to X

| X (points) | rose | both_see | alert_never | no_rise | mean lead (measurable) | mean lead (lower bound) |
|---|---|---|---|---|---|---|
| 5 | 8 | 4 | 4 | 3 | 0 | 21 |
| 10 | 5 | 3 | 2 | 6 | 0 | 21.2 |
| 15 | 5 | 3 | 2 | 6 | 0 | 21.2 |

## Result

Using the weekly score instead of band-crossing alerts improved the average time
from event to first visible rise from 25.2 days
(alert-only; a never-updating view counted as the full window, so this is a
lower bound on the gap) to 4 days, over the
5 of 11 event-material pairs where the score rose, at weekly
resolution. The whole gain comes from 2 pairs where alert-only never
updated; in the other 3 the two views agreed (lead 0 days), and
6 pairs had no rise.
