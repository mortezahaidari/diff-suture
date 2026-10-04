# Surgical Code Edits

> A portable Agent Skill for precise, standards-compliant code edits with minimal diff churn and local projected token-savings telemetry.

`surgical-code-edits` teaches coding agents to make the smallest correct change without sacrificing readability, formatting standards, maintainability, or correctness.

It is designed for the frustrating class of edits where a one-property, one-variable, or one-word change unexpectedly becomes a large delete-and-rewrite diff. The skill asks the agent to preserve unrelated content, edit the smallest useful construct, inspect the resulting diff, and correct unnecessary churn before finishing.

The repository also includes an optional local metrics helper that counts completed uses and estimates how much edit payload was avoided compared with rewriting changed files in full.

## Why this exists

Git records physical line changes, not semantic intent. If an agent reformats an object while adding one property, Git may report several deleted and added lines even though the meaningful change is tiny. The same problem appears when agents:

- Rewrite a whole function to rename one variable.
- Replace an entire component to change one label.
- Reorder imports that were unrelated to the task.
- Run a broad formatter for a local edit.
- Expand compact code without a style requirement.
- Leave simple code spread across many lines after deleting fields.
- Paste large unchanged blocks into tool calls or final responses.

These behaviors create noisy reviews, hide real changes, increase merge conflicts, and can consume more agent context and output tokens than necessary.

## What the skill does

When modifying existing files, the skill directs an agent to:

1. Search for the relevant code and inspect only the context it needs.
2. Identify the exact semantic change before writing.
3. Use a precise patch or replacement with the smallest practical hunk.
4. Preserve unrelated text, comments, ordering, whitespace, and line endings.
5. Follow the repository's formatter, linter, naming rules, and established style.
6. Expand or compact only the smallest changed construct when standards require it.
7. Remove only the requested code plus necessary syntactic cleanup.
8. Review the targeted diff and redo disproportionate or whitespace-only churn.
9. Report concise results without reproducing unchanged code.

The governing rule is:

> Correctness and maintainability first; smallest practical diff within those constraints.

## Example

Suppose the original type is:

```ts
run: { id: string; runNumber: string; periodKey: string; payDate: string; status: PayRunStatus }
```

The task is to add:

```ts
correction: PayRunDto['correction']
```

If the resulting line remains valid under the project's formatter and line-length rules, the preferred edit is:

```ts
run: { id: string; runNumber: string; periodKey: string; payDate: string; status: PayRunStatus; correction: PayRunDto['correction'] }
```

The skill discourages expanding the entire object merely because one property changed. However, it does not force compact code when the repository's standards require a multiline layout:

```ts
run: {
  id: string
  runNumber: string
  periodKey: string
  payDate: string
  status: PayRunStatus
  correction: PayRunDto['correction']
}
```

The inverse is also valid. If an edit removes enough fields that a multiline construct should become compact under the formatter or surrounding style, the agent may collapse that changed construct into one or a few lines. It should not reformat unrelated constructs nearby.

## What the skill does not do

The skill does not:

- Prefer tiny diffs over correct or maintainable code.
- Override repository-specific instructions.
- Prevent legitimate refactors, migrations, or generated-file updates.
- Guarantee lower model billing or account usage.
- Measure private provider token accounting.
- Send source code or metrics to an external service.
- Enforce behavior at the runtime or hook level; agents still interpret instructions.

Wider edits are appropriate when the user requests restructuring, generated files must be regenerated, an authoritative migration changes a broad surface, or a narrow patch would leave incoherent code.

## Supported agents

The repository uses the open `SKILL.md` Agent Skills format. It is intended to work with:

- OpenAI Codex
- Claude Code
- Cursor
- GitHub Copilot clients that support Agent Skills
- Other Agent Skills-compatible tools

Discovery directories differ by client. The same checkout can be linked into multiple discovery locations so every agent reads one canonical copy.

## Requirements

The instruction-only editing behavior requires an Agent Skills-compatible client.

The local usage metrics additionally require:

- Git
- Python 3.10 or newer
- A writable Git metadata directory or repository fallback directory

No third-party Python packages are required.

## Installation

### Recommended: one checkout shared by multiple agents

Clone the repository once:

```bash
git clone https://github.com/mortezahaidari/surgical-code-edits.git "$HOME/dev/surgical-code-edits"
```

Create shared Agent Skills and Claude Code links:

```bash
mkdir -p "$HOME/.agents/skills" "$HOME/.claude/skills"
ln -s "$HOME/dev/surgical-code-edits" "$HOME/.agents/skills/surgical-code-edits"
ln -s "$HOME/dev/surgical-code-edits" "$HOME/.claude/skills/surgical-code-edits"
```

The shared `.agents/skills` location is recognized by compatible clients such as Codex, Cursor, and GitHub Copilot. The `.claude/skills` link exposes the same canonical checkout to Claude Code.

### Direct per-client installation

If you use only one client, clone directly into its personal skill directory:

```bash
# Claude Code
git clone https://github.com/mortezahaidari/surgical-code-edits.git \
  "$HOME/.claude/skills/surgical-code-edits"

# Codex
git clone https://github.com/mortezahaidari/surgical-code-edits.git \
  "$HOME/.codex/skills/surgical-code-edits"

# Shared Agent Skills location
git clone https://github.com/mortezahaidari/surgical-code-edits.git \
  "$HOME/.agents/skills/surgical-code-edits"
```

Do not install multiple independent copies unless you intend to update each copy separately.

### Project-scoped installation

Teams can also place or link the repository under a project's supported skill directory, such as:

```text
<project>/.agents/skills/surgical-code-edits/
<project>/.claude/skills/surgical-code-edits/
<project>/.codex/skills/surgical-code-edits/
```

Use a Git submodule or symlink if you want the skill maintained independently from the application repository.

## Invocation

Explicit invocation names vary by client:

```text
Codex:      $surgical-code-edits
Claude Code: /surgical-code-edits
```

Example prompt:

```text
Use surgical-code-edits to add the correction field without changing unrelated formatting.
```

Compatible clients may also select the skill automatically when a task involves a focused modification to existing files.

After installing or updating a skill, start a new agent session if the current session does not refresh skill discovery automatically.

## Local usage metrics

The bundled [`scripts/usage_metrics.py`](scripts/usage_metrics.py) helper provides local feedback about how the skill is being used.

It records:

- Completed-use count
- Files observed and changed
- Binary files changed
- Lines added and deleted
- Estimated patch tokens
- Projected full-file rewrite tokens
- Projected tokens saved
- Projected savings percentage
- Average projected tokens saved per completed use

### How the projection works

For every changed UTF-8 text file, the helper:

1. Captures the file before the first edit.
2. Builds a unified diff with three context lines after editing.
3. Estimates patch tokens as `ceil(patch characters / 4)`.
4. Estimates a full rewrite as `ceil(final file characters / 4)`.
5. Reports the positive difference as projected tokens saved.

This is a transparent comparison model—not provider telemetry. Tokenization varies by model and language, and actual agent usage includes prompts, tool schemas, reasoning, file reads, cached context, and responses that this helper cannot observe.

For a small file, a patch can be larger than the full file because it contains headers and context. In that case, projected savings correctly reports zero instead of forcing a positive result.

### Automatic workflow

When an agent follows `SKILL.md`, it should:

```bash
# Before the first write
python3 <skill-root>/scripts/usage_metrics.py start <files...>

# Before changing an additional file not captured at start
python3 <skill-root>/scripts/usage_metrics.py track <session-id> <files...>

# After the final diff check
python3 <skill-root>/scripts/usage_metrics.py finish <session-id> --json
```

The agent should include the per-use and cumulative estimates in its final response.

### Manual commands

Start a measurement session:

```bash
python3 scripts/usage_metrics.py start src/example.ts
```

Track another file before editing it:

```bash
python3 scripts/usage_metrics.py track <session-id> src/another-file.ts
```

Finish and record a completed use:

```bash
python3 scripts/usage_metrics.py finish <session-id>
```

Return machine-readable output:

```bash
python3 scripts/usage_metrics.py finish <session-id> --json
```

Show cumulative history:

```bash
python3 scripts/usage_metrics.py report
python3 scripts/usage_metrics.py report --json
```

Cancel an unfinished session and remove its temporary snapshots:

```bash
python3 scripts/usage_metrics.py cancel <session-id>
```

### Example output

```text
Surgical edit use: #4
Files changed: 1 / 1
Lines changed: +1 / -1
Estimated patch tokens: ~123
Projected tokens saved: ~1467
Completed uses: 4
Cumulative projected tokens saved: ~5210
Average projected savings per use: ~1302.5
```

All token figures are estimates and should always be presented with that qualification.

## Metrics storage and privacy

The helper tries these storage locations in order:

1. `SURGICAL_EDIT_METRICS_DIR`, when explicitly configured.
2. `<git-directory>/surgical-code-edits/`.
3. `<repository>/.agent-data/surgical-code-edits/` as a fallback.

During an active session, the helper stores temporary snapshots of explicitly tracked files. On `finish` or `cancel`, those snapshots are removed.

Persistent files contain aggregate metrics only:

```text
usage.jsonl  Append-only aggregate history
latest.json Most recent completed result
```

No network requests are made. No source content is written to persistent history. If a process is interrupted before `finish` or `cancel`, its temporary session remains local until cancelled manually.

## Repository structure

```text
surgical-code-edits/
├── SKILL.md                 Agent-facing instructions and discovery metadata
├── README.md                Human-facing documentation
├── agents/
│   └── openai.yaml          OpenAI/Codex interface metadata
└── scripts/
    └── usage_metrics.py     Local measurement and reporting helper
```

`SKILL.md` intentionally remains concise because agents load it into context. Detailed explanations live here so routine invocation stays efficient.

## Updating

If installed from a shared checkout:

```bash
git -C "$HOME/dev/surgical-code-edits" pull --ff-only
```

Restart active agent sessions if they cache skill metadata.

## Uninstalling

Remove only the links or checkout you created. For the recommended shared installation:

```bash
rm "$HOME/.agents/skills/surgical-code-edits"
rm "$HOME/.claude/skills/surgical-code-edits"
rm -rf "$HOME/dev/surgical-code-edits"
```

Review each path before removal, especially if you installed a real directory instead of a symbolic link.

## Design principles

- **Correctness first:** Never preserve a tiny diff at the cost of broken or misleading code.
- **Standards-aware:** Respect project instructions, formatters, linters, naming, and language idioms.
- **Bidirectional formatting:** Expand or compact the changed construct when the established style requires it.
- **Proportional diffs:** Small semantic changes should usually produce small textual changes.
- **Scoped cleanup:** Remove newly unused imports or syntax made obsolete by the edit without refactoring unrelated code.
- **Transparent estimates:** Explain the token-savings model and never claim access to provider billing data.
- **Local privacy:** Keep snapshots and aggregate history on the user's machine.
- **Portable packaging:** Maintain one canonical skill that multiple compatible agents can discover.

## Contributing

Contributions should preserve the skill's narrow purpose. Useful changes include:

- Better detection or reporting of avoidable diff churn
- More accurate but still transparent estimation methods
- Cross-platform installation improvements
- Behavioral tests using realistic small-edit scenarios
- Documentation corrections for supported Agent Skills clients

Avoid adding broad coding-style opinions that belong in a project's own instructions. The skill should enforce proportional editing behavior while deferring to each repository's standards.

Before submitting a change:

1. Validate the skill manifest.
2. Run the metrics helper through `start`, `track`, `finish`, `report`, and `cancel` scenarios as relevant.
3. Confirm temporary source snapshots are removed after completion.
4. Confirm persistent history contains aggregate values only.
5. Review the final diff for unrelated formatting or generated artifacts.

## Security and trust

Agent skills are instructions that can influence tool use. Review `SKILL.md` and executable scripts before installation, especially when installing from forks or third-party repositories.

This skill does not require network access, API keys, credentials, or external services. The metrics helper reads only the files explicitly provided to it and stores its state locally.

## Repository description

Suggested GitHub description:

> Portable Agent Skill for precise, standards-compliant code edits with minimal diff churn and local projected token-savings telemetry.
