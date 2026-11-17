"""Delivery-policy eval: how many days earlier does the continuous score show
a rise than the alert-only (band-crossing) view does?

SCOPE / WHAT THIS IS NOT
  Both views are rendered from the SAME committed scores in
  backtest_output/backtest_results.csv. Only the delivery policy differs.
  The backtest's export-control signal was derived from the very event dates
  evaluated here (see snapshot/backtest.py), so this eval does NOT show that
  the score "detects" events. It compares two ways of showing the same scores.

  Nothing is re-fetched (no yfinance) and the CSV is read-only.

METRIC (per event x affected material)
  baseline   median of the (up to) 4 checkpoints strictly before the event date
  brief      the weekly score itself
  alert-only the score at the most recent band crossing (same logic as
             make_before_after_chart.py; stale between crossings)
  rise date  first checkpoint on/after the event date, within the window,
             where the view's value >= baseline + X   (X=10, window=56 days,
             window cut off at the next event on the same material)
  lead       alert-only rise date - brief rise date, in days
  Resolution is the CSV's checkpoint spacing (checked at runtime; weekly).

  Edge cases are counted separately, never dropped:
    no_rise        brief never reaches baseline + X in the window
    alert_never    brief rises, alert-only view never does -> censored,
                   lead is ">= window remaining", not a number
    both_see       both rise; lead is a plain number (may be 0)

Usage:
    python scripts/eval_delivery_policy.py
"""

from __future__ import annotations

import ast
import csv
import importlib.util
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "backtest_output"
CSV_PATH = OUT_DIR / "backtest_results.csv"

X_POINTS = 10
WINDOW_DAYS = 56
BASELINE_N = 4
BANDS = (40, 70)  # (low/moderate, moderate/elevated) -- as in the chart script


# ---------- inputs ----------------------------------------------------------

def load_events_and_affected():
    """Read EVENTS and the material sets from snapshot/backtest.py via ast, so
    the eval needs neither yfinance nor a re-run of the backtest."""
    tree = ast.parse((ROOT / "snapshot" / "backtest.py").read_text())
    events, consts = [], {}
    for node in tree.body:
        target = getattr(node, "target", None) or (
            node.targets[0] if isinstance(node, ast.Assign) else None)
        name = getattr(target, "id", None)
        if name == "EVENTS":
            for call in node.value.elts:
                a = call.args
                d = date(*(c.value for c in a[0].args))
                events.append((d, ast.literal_eval(a[1])))
        elif name in ("HEAVY_REE_MATERIALS", "INDIUM_MATERIAL"):
            consts[name] = ast.literal_eval(node.value)
    # Mirrors export_intensity(): event 0 -> Indium, events 1.. -> heavy REE.
    affected = [
        [consts["INDIUM_MATERIAL"]] if i == 0 else sorted(consts["HEAVY_REE_MATERIALS"])
        for i in range(len(events))
    ]
    return events, affected


def load_series():
    rows = list(csv.DictReader(open(CSV_PATH)))
    series: dict[str, list[tuple[date, int]]] = {}
    for r in rows:
        series.setdefault(r["material"], []).append(
            (datetime.strptime(r["date"], "%Y-%m-%d").date(), int(r["score"])))
    for v in series.values():
        v.sort()
    return series


def spacing(series):
    dates = [d for d, _ in next(iter(series.values()))]
    gaps = sorted({(b - a).days for a, b in zip(dates, dates[1:])})
    return dates[0], dates[-1], len(dates), gaps


# ---------- views -----------------------------------------------------------

def band(score, lo, hi):
    return "elevated" if score >= hi else "moderate" if score >= lo else "low"


def alert_view(scores, lo, hi):
    """Same logic as make_before_after_chart.py, with parametrised bands."""
    out, last_band, last_val = [], None, scores[0]
    for s in scores:
        b = band(s, lo, hi)
        if b != last_band:
            last_val, last_band = s, b
        out.append(last_val)
    return out


# ---------- core metric -----------------------------------------------------

def evaluate_pair(pts, ev_date, next_ev_date, lo, hi, x=X_POINTS):
    dates = [d for d, _ in pts]
    scores = [s for _, s in pts]
    before = [s for d, s in pts if d < ev_date][-BASELINE_N:]
    base = statistics.median(before)
    end = ev_date + timedelta(days=WINDOW_DAYS)
    if next_ev_date:
        end = min(end, next_ev_date - timedelta(days=1))
    alert = alert_view(scores, lo, hi)
    idx = [i for i, d in enumerate(dates) if ev_date <= d <= end]

    def first(vals):
        for i in idx:
            if vals[i] >= base + x:
                return dates[i]
        return None

    b, a = first(scores), first(alert)
    res = {"baseline": base, "brief_date": b, "alert_date": a,
           "window_days": (end - ev_date).days}
    if b is None:
        res.update(status="no_rise", lead=None)
    elif a is None:
        res.update(status="alert_never", lead=None)
    else:
        res.update(status="both_see", lead=(a - b).days)
    # days from event to first visible rise, per view (None if never)
    res["brief_days"] = (b - ev_date).days if b else None
    res["alert_days"] = (a - ev_date).days if a else None
    return res


def run_all(series, events, affected, lo, hi, x=X_POINTS):
    out = []
    for i, (ev_date, label) in enumerate(events):
        for m in affected[i]:
            # cut-off: next event that affects this same material
            nxt = next((events[j][0] for j in range(i + 1, len(events))
                        if m in affected[j]), None)
            r = evaluate_pair(series[m], ev_date, nxt, lo, hi, x)
            r.update(event_idx=i, event=label, event_date=ev_date, material=m)
            out.append(r)
    return out


def summarize(res):
    both = [r for r in res if r["status"] == "both_see"]
    never = [r for r in res if r["status"] == "alert_never"]
    norise = [r for r in res if r["status"] == "no_rise"]
    rose = both + never
    s = {"pairs": len(res), "both_see": len(both), "alert_never": len(never),
         "no_rise": len(norise)}
    s["mean_lead_measurable"] = (statistics.mean(r["lead"] for r in both)
                                 if both else None)
    # Lower bound: a never-updating alert view counts as the full window
    # remaining after the brief's rise (censored => true lead is >= this).
    if rose:
        caps = [r["lead"] if r["status"] == "both_see"
                else r["window_days"] - r["brief_days"] for r in rose]
        s["mean_lead_lower_bound"] = statistics.mean(caps)
        s["brief_mean_days"] = statistics.mean(r["brief_days"] for r in rose)
        s["alert_mean_days_capped"] = statistics.mean(
            r["alert_days"] if r["alert_days"] is not None else r["window_days"]
            for r in rose)
    else:
        s["mean_lead_lower_bound"] = s["brief_mean_days"] = None
        s["alert_mean_days_capped"] = None
    return s


# ---------- reporting -------------------------------------------------------

def fmt(v, nd=1):
    return "-" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def pair_table(res):
    lines = ["| Event | Date | Material | Baseline | Brief rise (d after event) | "
             "Alert-only rise (d after event) | Lead (d) | Status |",
             "|---|---|---|---|---|---|---|---|"]
    for r in res:
        lead = r["lead"] if r["status"] == "both_see" else (
            f">={r['window_days'] - r['brief_days']} (censored)"
            if r["status"] == "alert_never" else "-")
        lines.append(f"| {r['event']} | {r['event_date']} | {r['material']} | "
                     f"{fmt(r['baseline'])} | {fmt(r['brief_days'])} | "
                     f"{fmt(r['alert_days'])} | {lead} | {r['status']} |")
    return "\n".join(lines)


def event_rollup(res, events):
    lines = ["| Event | Date | Pairs | both_see | alert_never | no_rise |",
             "|---|---|---|---|---|---|"]
    for i, (d, label) in enumerate(events):
        rs = [r for r in res if r["event_idx"] == i]
        c = lambda k: sum(r["status"] == k for r in rs)
        lines.append(f"| {label} | {d} | {len(rs)} | {c('both_see')} | "
                     f"{c('alert_never')} | {c('no_rise')} |")
    return "\n".join(lines)


def band_sensitivity(series, events, affected):
    los, his = range(30, 51, 5), range(60, 81, 5)
    lines = ["Cells: both_see/alert_never/no_rise ; mean lead lower bound (days)",
             "", "| low/mod \\ mod/elev | " + " | ".join(map(str, his)) + " |",
             "|---|" + "---|" * len(his)]
    grid = {}
    for lo in los:
        cells = []
        for hi in his:
            s = summarize(run_all(series, events, affected, lo, hi))
            grid[(lo, hi)] = s
            cells.append(f"{s['both_see']}/{s['alert_never']}/{s['no_rise']} ; "
                         f"{fmt(s['mean_lead_lower_bound'])}d")
        lines.append(f"| {lo} | " + " | ".join(cells) + " |")
    return "\n".join(lines), grid


def x_sensitivity(series, events, affected):
    lines = ["| X (points) | rose | both_see | alert_never | no_rise | "
             "mean lead (measurable) | mean lead (lower bound) |",
             "|---|---|---|---|---|---|---|"]
    for x in (5, 10, 15):
        s = summarize(run_all(series, events, affected, *BANDS, x=x))
        lines.append(f"| {x} | {s['both_see'] + s['alert_never']} | {s['both_see']} | "
                     f"{s['alert_never']} | {s['no_rise']} | "
                     f"{fmt(s['mean_lead_measurable'])} | "
                     f"{fmt(s['mean_lead_lower_bound'])} |")
    return "\n".join(lines)


def main():
    series = load_series()
    events, affected = load_events_and_affected()
    first, last, n, gaps = spacing(series)
    resolution = (f"{gaps[0]}-day (weekly)" if gaps == [7] else f"mixed {gaps}")

    # Guard against drift from the chart script's band(): extract that function
    # with ast (importing the script would require matplotlib) and compare.
    src = ast.parse((Path(__file__).with_name("make_before_after_chart.py")).read_text())
    fn = next(n for n in src.body if isinstance(n, ast.FunctionDef) and n.name == "band")
    ns: dict = {}
    exec(compile(ast.Module([fn], []), "chart_band", "exec"), ns)
    assert all(ns["band"](s) == band(s, *BANDS) for s in range(101)), \
        "band() drifted from make_before_after_chart.py"
    print("band() parity with make_before_after_chart.py: OK")

    res = run_all(series, events, affected, *BANDS)
    s = summarize(res)
    sens, grid = band_sensitivity(series, events, affected)

    report = f"""# Delivery-policy eval: weekly score vs alert-only (band crossing)

**Scope.** Both views come from the same committed scores
(`backtest_output/backtest_results.csv`); only the delivery policy differs.
The backtest's export-control signal was derived from these same event dates,
so this does **not** show the score "detects" events. It compares two ways of
showing identical scores.

**Resolution.** {n} checkpoints, {first} to {last}, spacing {resolution}.
Leads are multiples of 7 days; they are not daily-precision results. Event dates
mostly fall between checkpoints, so "days after event" is to the next checkpoint.

**Definition.** baseline = median of the up-to-{BASELINE_N} checkpoints strictly before
the event. Rise date = first checkpoint on/after the event, within
{WINDOW_DAYS} days (cut off at the next event on the same material), where the view's
value >= baseline + {X_POINTS}. Lead = alert-only rise date - brief rise date.
Alert-only value = score at the latest band crossing (bands {BANDS[0]}/{BANDS[1]}).
Affected materials follow `export_intensity()`: Indium for event 1, Dysprosium and
Yttrium for events 2-6. Note: event 6 (EU entity ban) has no step in the backtest's
export signal (level already 4 from event 5), so it cannot move the score.

## Per event x material ({s['pairs']} pairs from {len(events)} events)

{pair_table(res)}

## Event rollup

{event_rollup(res, events)}

## Counts

- both_see: {s['both_see']}  (plain lead; mean lead = {fmt(s['mean_lead_measurable'])} days)
- alert_never (brief rises, alert-only view never updates; censored): {s['alert_never']}
- no_rise (brief itself never rises >= {X_POINTS}): {s['no_rise']}

Mean lead counting alert_never as the remaining window (a LOWER BOUND):
{fmt(s['mean_lead_lower_bound'])} days over the {s['both_see'] + s['alert_never']} pairs with a rise.
Mean days from event to first visible rise (same pairs): brief
{fmt(s['brief_mean_days'])} vs alert-only {fmt(s['alert_mean_days_capped'])}
(alert-only capped at the window where it never updates).

## Sensitivity to band boundaries

{sens}

## Sensitivity to X

{x_sensitivity(series, events, affected)}

## Result

Using the weekly score instead of band-crossing alerts improved the average time
from event to first visible rise from {fmt(s['alert_mean_days_capped'])} days
(alert-only; a never-updating view counted as the full window, so this is a
lower bound on the gap) to {fmt(s['brief_mean_days'])} days, over the
{s['both_see'] + s['alert_never']} of {s['pairs']} event-material pairs where the score rose, at weekly
resolution. The whole gain comes from {s['alert_never']} pairs where alert-only never
updated; in the other {s['both_see']} the two views agreed (lead 0 days), and
{s['no_rise']} pairs had no rise.
"""
    (OUT_DIR / "delivery_policy_eval.md").write_text(report)

    with open(OUT_DIR / "delivery_policy_eval_pairs.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["event", "event_date", "material", "baseline", "brief_date",
                    "alert_date", "brief_days", "alert_days", "lead_days", "status",
                    "window_days"])
        for r in res:
            w.writerow([r["event"], r["event_date"], r["material"], r["baseline"],
                        r["brief_date"], r["alert_date"], r["brief_days"],
                        r["alert_days"], r["lead"], r["status"], r["window_days"]])
    with open(OUT_DIR / "delivery_policy_eval_band_sensitivity.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["low_mod", "mod_elev", "both_see", "alert_never", "no_rise",
                    "mean_lead_measurable", "mean_lead_lower_bound"])
        for (lo, hi), g in grid.items():
            w.writerow([lo, hi, g["both_see"], g["alert_never"], g["no_rise"],
                        g["mean_lead_measurable"], g["mean_lead_lower_bound"]])
    print(report)


if __name__ == "__main__":
    main()
