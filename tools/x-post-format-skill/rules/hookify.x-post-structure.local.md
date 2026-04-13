---
name: x-post-format-only
enabled: true
event: prompt
action: warn
pattern: .
---

Formatting-only guardrail:

1. Preserve original text exactly.
2. Do not add/remove/replace/reorder any non-whitespace character.
3. Do not change punctuation marks or emoji.
4. Only adjust spaces, line breaks, and blank lines.
5. Use flexible segmentation, not rigid splitting:
   - Prefer 2-5 paragraphs (short) or 3-6 (long).
   - Prefer 1 sentence per paragraph; allow 2 when tightly coupled.
   - Break on emotion opening, topic turns, and long dense clauses.
6. Output final body only.
