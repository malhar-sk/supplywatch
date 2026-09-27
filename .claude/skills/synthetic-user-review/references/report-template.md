# Report Template

Fill in every bracketed field with real content. Never leave a literal
`[bracket]` placeholder in the saved file — if something genuinely could not
be observed, say so in prose ("Guest Mode: not reachable, connection refused")
rather than leaving the placeholder unfilled.

If the review was skipped (see SKILL.md §0), use the SKIPPED variant at the
bottom of this file instead of the full template.

---

## REVIEWED variant

```markdown
# Synthetic User Review — [ISO 8601 timestamp]

## Status
REVIEWED

## Target reviewed
http://localhost:8501

## Persona lens applied
[one-line reminder of who's reviewing, e.g. "Small precision-hardware/magnets
manufacturer, 1-2 suppliers per material, no dedicated risk role, ~30-60s
patience per visit."]

## Pages walked
- Daily Brief: [what was observed, in the persona's own terms]
- Guest Mode: [...]
- Portfolio View: [...]
- Risk Map: [...]

## UX critique
- [Finding tied to a specific page/element. Not generic — name the exact
  thing that helped or hurt the 30-second-glance goal.]

## Efficiency suggestions
- [Current friction] → [proposed reduction]

## Feature prioritization (persona lens only)
1. [Highest-value-to-persona item and why — "gets me to check tomorrow"]
2. [...]
3. [...]

## Scope-creep flags
- [Feature/element] — verdict: [KEEP | FLAG] — "Would I actually want, use, or
  pay for this, given I have no dedicated risk role, 1-2 suppliers per
  material, and no enterprise budget?" → [answer in persona's own reasoning]

## Overall verdict
[One paragraph: does this still feel like a low-friction daily habit today?
Would the persona actually come back tomorrow?]

## Diff context (commit only — NOT used to form any judgment above)
- Commit: [hash] — [subject line]
```

---

## SKIPPED variant

```markdown
# Synthetic User Review — [ISO 8601 timestamp]

## Status
SKIPPED: [short reason, e.g. "browser tool unreachable after one retry" or
"dashboard did not respond at http://localhost:8501 within timeout"]

## What was attempted
[Plain description of what was tried before giving up — e.g. "Probed for a
browser automation tool via ToolSearch, none resolved. Retried once after 5s.
Still unavailable."]

## Target reviewed
[URL attempted, or "not reached"]

## Diff context (commit only)
- Commit: [hash] — [subject line]
```
