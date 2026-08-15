# Reporting Skill and Artifacts Layout — Completion Report

## Summary

Added a repository-local `final-report` Agent Skill and standardized Direttore task-completion reports under `artifacts/` with sortable `YYYY-MM-DD-<task-slug>-report.md` filenames. Removed the existing slot-centric refactor report from the repository root and updated repository guidance so durable migration/documentation files are not created merely because a task completed.

## Files changed

- `.agents/skills/final-report/SKILL.md` — new Agent Skill defining when and how Codex should write final task reports, including required frontmatter, report structure, validation rules, and dated artifact naming.
- `AGENT.md` — completion-report policy now points to the repository skill; migration/documentation updates are conditional on actual public/documented changes.
- `README.md` — root-level refactor-report link replaced with the dated report under `artifacts/`.
- `artifacts/2026-08-03-slot-centric-refactor-report.md` — existing `REFACTOR_REPORT.md` moved out of the repository root and date-prefixed using its last-modified date.
- `artifacts/2026-08-15-reporting-skill-and-artifacts-report.md` — this report.

## Implementation notes

The skill follows the Agent Skills `SKILL.md` structure with required `name` and `description` YAML frontmatter. The description explicitly covers completed repository work so Codex can select the skill by task relevance.

`MIGRATION.md` was intentionally kept in the repository root because it is durable migration documentation referenced by the README, not a task-completion artifact. Rough working notes were not moved as part of this focused reporting-layout change.

## Tests and validation

- Filesystem creation of `.agents/skills/final-report/`, `artifacts/`, and `SKILL.md` — passed.
- Read-back verification of the skill, `AGENT.md`, and `README.md` — passed.
- Source-code tests, Ruff, and Pyright — Not run; no Python implementation behavior changed, and the connected local filesystem tool does not provide command execution.

## Unresolved items

- The canonical Google Drive `direttore` Codex-instructions tab still needs the same completion-report rule synchronized when the Google Drive write connector is exposed in the session.

## Suggested follow-ups

- On the next fresh Codex session, confirm that `final-report` appears in the available project skills and is selected automatically for a completed repository task.

## Proposed git commit message

`Add final-report skill and dated artifacts layout`
