# X Post Formatting Skill

This package combines two layers:

1. Hookify rules for formatting-only constraints (zero rewrite).
2. Prettier + markdownlint-cli2 for final formatting cleanup.

## Files

- `SKILL.md`: skill definition and workflow.
- `rules/hookify.x-post-structure.local.md`: prompt-time structure guardrail.
- `rules/hookify.x-post-stop-check.local.md`: stop-time reminder to run final cleanup.
- `scripts/clean-x-post.ps1`: one-command formatter pipeline.
- `scripts/clean-x-post.cmd`: Windows wrapper for easier execution.
- `.markdownlint.json`: markdownlint profile tuned for content snippets.

## Quick Start

1. Copy Hookify rules into your project `.claude/` directory.
2. Put content into a `.md` file (for example `draft.md`).
3. Run:

```cmd
scripts\clean-x-post.cmd draft.md
```

If you prefer PowerShell directly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\clean-x-post.ps1 -InputPath .\draft.md
```

## Notes

- This is formatting-only enforcement (zero rewrite), not content rewriting.
- Non-whitespace characters should remain unchanged after formatting.
- Layout is flexible: it should split by meaning and rhythm, not by a fixed line count.
- If you need strict character limits, add a post-step in product code.
- The first run may download npm tools through `npx` (`prettier`, `markdownlint-cli2`).
