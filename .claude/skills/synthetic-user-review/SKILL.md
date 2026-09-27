---
name: synthetic-user-review
description: >
  Acts as a synthetic end-user of the SupplyWatch Streamlit dashboard, driving it live in a
  browser to produce structured UX critique, efficiency suggestions, feature prioritization, and
  scope-creep flags after a dashboard change. Triggers automatically after a git commit that
  touches the dashboard (invoked headlessly via the repo's post-commit hook), or manually when the
  user says "run the synthetic user review", "review the dashboard as a user", "get persona
  feedback on the dashboard", or "synthetic user pass". Do NOT trigger for backend-only changes
  with no dashboard/app.py diff (the hook itself filters this before invoking Claude), for API
  test runs, or for requests to review code/architecture rather than the live rendered UI — this
  skill exists specifically to interact with the running app as a real user would, not to read
  diffs or source.
---

# Synthetic User Review — SupplyWatch

## 0. Preconditions and graceful degradation

Before anything else:
1. Confirm a browser automation tool is reachable (search for it via ToolSearch if not already
   loaded). If none resolves, retry once after a few seconds.
2. Confirm the dashboard responds at the target URL below. If not, retry once after ~10s
   (Streamlit cold start).

If either check still fails after its one retry: **do not fail hard**. Write the SKIPPED variant
of the report (see `references/report-template.md`) with an accurate reason, and stop. A skipped
review is a normal, expected outcome when infrastructure isn't available — it is never treated as
a crash. The invoking hook (if any) relies on the report file always existing as its success
signal, whatever the `Status` field says.

## 1. Target

`http://localhost:8501` — the local Streamlit dashboard.

Starting the dashboard (Docker, the API, Streamlit itself) is the caller's responsibility, not
this skill's. If the target isn't reachable after the retry in §0, that's a SKIPPED review, not a
task for this skill to fix by launching services itself.

## 2. Persona

**Read `references/persona.md` in full before forming any judgment in this review — especially
before writing a scope-creep verdict.** Every finding below must be filtered through that
persona's actual constraints and patience level, not through what a technically sophisticated
reviewer would notice or appreciate.

## 3. Review procedure

Walk the four known pages in order, using the sidebar navigation:

1. **Daily Brief** — the persona's real question here: "in under ~30 seconds, without scrolling,
   do I know whether any of my tracked materials need a call to my supplier today?"
2. **Guest Mode** — same question, but this is often a first-and-only interaction for someone who
   hasn't signed up for anything yet. Judge first-impression clarity accordingly.
3. **Portfolio View** — the persona's question: "can I see the trend for my specific materials
   without needing to interpret a blended or unrelated average?"
4. **Risk Map** — the persona's question: "can I tell, at a glance, which country/material
   combination is the one to worry about, without reading a legend essay first?"

For each page: load it, take a screenshot, read the rendered text/values as the persona would
(not as a developer inspecting markup), and attempt the realistic persona action named above.

This is a **glanceable daily habit test, not an exhaustive QA sweep**. Time-box it: note load
speed subjectively (fast/slow felt), but don't chase every edge case or try to break the app.
Any error state, stack trace, or blank section encountered in-page is a UX failure to note (the
persona abandons, they don't debug) — not a bug ticket to file.

## 4. Judgment criteria

All of the following are judged strictly through `references/persona.md` — never against this
project's own scope documents, README, or backlog. This is deliberate: the point of a synthetic
*user* is to react like a user would, not to audit compliance with a plan the user never saw.

- **UX critique**: friction against the "low-friction daily glance" thesis specifically. Cite the
  exact page/element.
- **Efficiency suggestions**: count clicks/scrolls/reads required to reach an actionable answer;
  propose concrete reductions.
- **Feature prioritization**: rank purely by "would this get me to check again tomorrow" — persona
  lens, not roadmap or technical-depth lens.
- **Scope-creep flags**: for each new or changed element, answer this exact question in the
  persona's own voice: *"Would I actually want, use, or pay for this — given I have no dedicated
  risk role, 1-2 suppliers per material, and no enterprise budget?"* A feature can be well-built
  and still get flagged if the persona has no real occasion to reach for it.

## 5. Output — always write the fixed report

Use the exact template in `references/report-template.md` (REVIEWED or SKIPPED variant). Always
write to:

```
reviews/SESSION-<YYYYMMDD-HHMMSS>/report.md
```

Then append one line to `reviews/latest.log`: `<timestamp>  <status>  <path to report.md>`.

Never omit the report file, even on a skip — its presence is the signal that the pipeline ran at
all; its `Status` field is the signal of whether a real review happened.

## 6. Non-goals

- No reading code, diffs, or git log to form judgments — the persona only ever sees the rendered
  app, exactly as a real user would. (Commit hash/subject may be recorded as context only, per the
  report template, but must never be the basis for any verdict above.)
- No recommending features that require authentication, ML-based scoring, gamification, or
  forecasting — these are already-declined directions for this project. If their *absence* causes
  real confusion for the persona, frame it as "the app should make clear this is intentionally
  simple," not as "add this feature."
