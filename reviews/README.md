# reviews/

Output of the `synthetic-user-review` skill, run automatically by
`hooks/post-commit` after any commit that touches the dashboard.

- `SESSION-<timestamp>/report.md` — the actual persona-based feedback for that
  run (or a `SKIPPED` note if the dashboard/browser tooling wasn't reachable).
- `SESSION-<timestamp>/claude-invocation.log` — raw output from the headless
  `claude -p` call, for debugging the pipeline itself, not persona-facing.
- `latest.log` — one line per run (`timestamp  status  path`), append-only,
  for a quick `tail` without opening a session folder.

Session subfolders are working artifacts and are gitignored — only this
README (and the `.gitignore` itself) are tracked.

To enable the hook that populates this directory (once per clone):

```
git config core.hooksPath hooks
```
