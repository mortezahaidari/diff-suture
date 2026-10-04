# Surgical Code Edits

A portable Agent Skill for making precise code changes without unnecessary file rewrites, formatting churn, or oversized diffs.

The skill prioritizes correctness, repository standards, readability, and maintainability. Within those constraints, it changes only the smallest necessary construct and preserves unrelated content byte-for-byte.

## Supported agents

The `SKILL.md` format follows the open Agent Skills convention and can be discovered by Codex, Claude Code, Cursor, GitHub Copilot, and other compatible agents.

## Install

Clone once, then expose the checkout through the discovery directories used by your agents:

```bash
git clone https://github.com/mortezahaidari/surgical-code-edits.git "$HOME/dev/surgical-code-edits"
mkdir -p "$HOME/.agents/skills" "$HOME/.claude/skills"
ln -s "$HOME/dev/surgical-code-edits" "$HOME/.agents/skills/surgical-code-edits"
ln -s "$HOME/dev/surgical-code-edits" "$HOME/.claude/skills/surgical-code-edits"
```

Use `$surgical-code-edits` in Codex or `/surgical-code-edits` in Claude Code. Compatible agents may also select it automatically when modifying existing files.

## Local usage metrics

The bundled `scripts/usage_metrics.py` records completed uses and estimates the edit payload saved compared with rewriting each changed text file in full. It reports per-use and cumulative file, line, and projected-token metrics in human-readable or JSON form.

Metrics remain local. Temporary source snapshots are deleted after completion or cancellation, and persistent history contains aggregate counts only. Projected token savings are estimates—not actual model, context-window, billed, or account token usage.
