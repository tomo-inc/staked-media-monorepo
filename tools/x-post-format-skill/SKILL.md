---
name: x-post-formatting
description: Format X/Twitter post text without rewriting content, then apply final cleanup using Prettier + markdownlint-cli2.
license: MIT
---

# Mission

Format X/Twitter post text with clean markdown layout while preserving original wording exactly.

# Inputs

- raw post content (Chinese or English)

# Output

- cleaned markdown text
- no extra commentary

# Constraints

- zero-rewrite mode:
  - do not add, remove, replace, or reorder any non-whitespace character
  - do not change punctuation marks or emoji
  - do not introduce markdown markers such as headings, bullets, or numbering
- formatting-only operations allowed:
  - insert/remove line breaks
  - adjust spaces and blank lines
  - split long text into readable paragraphs

# Flexible Layout Heuristics

- Keep layout readable but not rigid; apply context-aware paragraph breaks.
- Prefer 2 to 5 paragraphs for short copy, 3 to 6 for long copy.
- Prefer 1 sentence per paragraph; allow 2 sentences when meaning is tightly coupled.
- Prioritize breaks at:
  - emotional opening fragments (for example lines starting with emoji or exclamation)
  - topic turns (for example "but", "however", "then", "result", "so", or equivalent transition words)
  - high-density long clauses split into digestible chunks
- Do not force every comma into a line break.
- Keep quote marks paired in the same paragraph whenever possible.

# Workflow

1. Save original content as markdown.
2. Apply Hookify guardrails (prompt + stop checks).
3. Run formatting-only cleanup.
4. Run cleanup script:

```powershell
./scripts/clean-x-post.ps1 -InputPath ./draft.md
```

5. Publish only the cleaned output.

# Integration Hint

In product code, run this skill as a formatting pipeline:

1. preserve original text exactly
2. apply whitespace-only layout changes
3. run Prettier + markdownlint-cli2 before final output
4. if layout is too flat, re-segment using the flexible heuristics above
