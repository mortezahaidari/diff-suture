---
name: diff-suture
description: "Make precise edits to existing code: change or delete only the necessary lines, preserve unchanged text, and avoid whole-block or whole-file rewrites. Use for fixes, refactors, renames, and copy edits where minimal diff churn matters."
---

# Diff Suture

Minimize edit and context churn while preserving correctness. A small requested change should produce a proportionally small diff.

## Editing behavior

- Inspect only the files and narrow regions needed to understand the change. Search first; avoid printing or rereading whole files when a targeted view is enough.
- Use a patch or precise replacement with the smallest practical hunk. Keep unchanged lines byte-for-byte identical.
- For a wording, literal, property, or variable change, modify that token or line only. Do not recreate the surrounding function, object, component, or file.
- Follow the repository's established coding standards, formatter, linter, naming, and readability conventions. A smaller diff does not justify dense, inconsistent, invalid, or less maintainable code.
- Preserve the existing compact or expanded representation when it remains compliant and readable. When the changed construct should be expanded or compacted under the repository's formatter, line-length rules, or established style, reflow only that smallest enclosing construct into the standard form; this applies in both directions, including collapsing many lines into one or a few lines.
- For deletion, remove only the requested span and the minimum cleanup needed to keep syntax, imports, and spacing valid.
- Preserve existing formatting, comments, import order, line endings, and nearby whitespace unless the task requires changing them.
- Do not run broad formatters, generators, or automated rewrites for a local edit. When formatting is required, scope it to changed files and check that it did not alter unrelated code.
- Do not paste unchanged code into progress updates or the final response. Summarize the result and reference the changed files or lines.

## Diff check

After each coherent edit batch, inspect the targeted diff. Use the repository's normal diff tooling; for Git repositories, prefer `git diff -- <changed-paths>` and `git diff --check`.

If the diff is larger than the requested behavior warrants, contains whitespace-only churn, or deletes and re-adds equivalent text, redo the edit more narrowly before continuing.

## Usage feedback

For edits performed with this skill, use the bundled `scripts/usage_metrics.py` by its path relative to this `SKILL.md`:

1. After identifying the target files and before the first write, run `python3 <skill-root>/scripts/usage_metrics.py start <files...>` and retain the returned session ID.
2. Before modifying an additional file that was not captured at start, run `python3 <skill-root>/scripts/usage_metrics.py track <session-id> <files...>`.
3. After the final diff check, run `python3 <skill-root>/scripts/usage_metrics.py finish <session-id> --json`.
4. Include the per-use and cumulative metrics in the final response: completed-use number, files changed, lines added and deleted, estimated patch tokens, projected tokens saved, and average projected savings per use.

The projection compares an estimated three-context-line patch payload with rewriting each changed text file in full. It uses four text characters per token. Label it as an estimate, never as actual model, context-window, billed, or account token usage.

Metrics stay local. Temporary source snapshots are removed after `finish` or `cancel`; persistent history contains aggregate counts only. If measurement cannot run, continue the requested edit, report metrics as unavailable, and never invent values. Use `python3 <skill-root>/scripts/usage_metrics.py report` to show cumulative history.

## Necessary exceptions

Correctness and maintainability take priority over the smallest possible line count. A wider rewrite is appropriate when the user requests restructuring, generated files must be regenerated, an automated migration is authoritative, or a local patch would leave incoherent code. Keep the rewrite scoped and briefly state why it was necessary.
