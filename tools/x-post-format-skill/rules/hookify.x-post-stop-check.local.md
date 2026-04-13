---
name: x-post-stop-check
enabled: true
event: stop
action: warn
conditions:
  - field: transcript
    operator: regex_match
    pattern: (Twitter|X\s*post|tweet|推文|文案)
  - field: transcript
    operator: not_contains
    pattern: clean-x-post.ps1
---

Final cleanup step appears to be missing.

Before ending, run:

`./scripts/clean-x-post.ps1 -InputPath <your-file>.md`

This ensures Prettier + markdownlint-cli2 cleanup is applied.
Reminder: keep zero-rewrite mode (only whitespace and line-break changes).
