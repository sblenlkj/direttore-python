---
name: final-report
description: Create the factual completion report for a finished Direttore repository task. Use after code, tests, documentation, examples, benchmarks, or project structure were changed and the work is ready for review. Store the report under artifacts/ with a sortable YYYY-MM-DD date prefix; never create task-completion reports in the repository root.
---

# Final Report

Use this skill at the end of a completed Direttore repository task that changed code, tests, documentation, examples, benchmarks, or project structure.

## Purpose

Create exactly one concise, factual Markdown completion report for review. The report records what actually changed and what was actually validated. It is not a plan, design proposal, changelog, migration guide, or replacement for repository documentation.

All task-completion reports belong under `artifacts/`. Do not place refactor reports, Codex completion reports, benchmark summaries, migration-task reports, or similar temporary task artifacts in the repository root.

Durable project documentation remains where the repository already defines it. For example, update an existing `MIGRATION.md`, README, or file under `docs/` only when the task actually changes the durable documentation they describe. Do not create a new migration document merely because a task was completed.

## Output location and naming

Write the report to:

`artifacts/YYYY-MM-DD-<task-slug>-report.md`

Use the local calendar date on which the report is written, followed by a short task-specific kebab-case slug. The leading ISO date is mandatory so ordinary filename sorting is chronological.

Examples:

- `artifacts/2026-08-15-slot-lease-cleanup-report.md`
- `artifacts/2026-08-15-resolver-cache-benchmark-report.md`
- `artifacts/2026-08-15-saga-journal-contract-report.md`

Do not overwrite an unrelated report. If the natural filename already exists, choose a more specific task slug rather than adding an arbitrary counter.

## Before writing

Inspect the completed work first. Use the repository state as the source of truth:

- inspect the relevant diff/status;
- identify the important files actually changed;
- distinguish completed work from deferred or unimplemented work;
- record only tests, checks, and benchmarks that were actually run;
- if a requested validation step was not run or could not run, say so explicitly.

Do not infer success from intended behavior or from the original task specification.

## Required report structure

Use this structure unless a section is genuinely irrelevant:

```markdown
# <Task title> — Completion Report

## Summary

Briefly state what was completed and the resulting behavior or repository state.

## Files changed

List the important changed files or packages and the role of each change. Do not dump every generated or incidental file unless it matters to review.

## Implementation notes

Record important implementation decisions, preserved invariants, compatibility considerations, and any material deviation from the original task.

## Tests and validation

List commands actually run and their outcomes.

Examples:
- `pytest ...` — passed
- `ruff check ...` — passed
- `pyright` — passed
- targeted smoke test — passed

If something was not run, write `Not run` and explain why when relevant.

## Benchmarks

Include only when performance was part of the task. Record the command/scenario and measured result. Never make benchmark claims without measurements.

## Unresolved items

List anything incomplete, blocked, uncertain, intentionally deferred, or discovered during the task. Write `None` when there are no material unresolved items.

## Suggested follow-ups

Include only concrete follow-up work that is useful because of this task. Do not add generic cleanup suggestions.

## Proposed git commit message

`<concise commit title>`
```

## Reporting rules

- Describe what actually happened, not what was originally requested.
- Keep the report concise and reviewable; name code instead of copying large code blocks.
- Separate verified facts from assumptions or recommendations.
- Preserve failures and incomplete validation in the report; never fabricate a green result.
- Mention public API or semantic changes explicitly.
- Mention lifecycle, cleanup, concurrency, transaction, or caching implications when they were materially affected.
- Mention benchmark results only when an appropriate benchmark was actually executed.
- Do not create a git commit, push, tag, or rewrite history as part of this skill.
- Propose exactly one commit message; do not execute it.
- Do not create additional root-level summary/report Markdown files unless the task explicitly requires durable repository documentation.

## Completion condition

The repository task is not fully handed off for review until the report exists under `artifacts/` with the required date prefix and accurately reflects the final repository state.
