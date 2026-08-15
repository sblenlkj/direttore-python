# Direttore repository cleanup — Completion Report

## Summary

Cleaned repository-only artifacts and consolidated documentation without
changing Python behavior or public APIs. All working-tree `.DS_Store` files are
gone and future occurrences are ignored, Codex instructions now use
`AGENTS.md`, stale scratch and source-local design notes were removed, and the
two useful details from removed package notes were preserved in the canonical
core guide.

## Files changed

- `.gitignore` — ignores `.DS_Store` at every repository depth.
- `.DS_Store`, `src/.DS_Store`, and `src/direttore/.DS_Store` — removed.
- `AGENT.md` -> `AGENTS.md` — renamed while preserving the current instruction
  content, including the repository-local completion-report policy.
- `notes.md` and `saga_notes.md` — removed as stale engine/query-era and early
  saga scratch notes; their current concepts are already represented by the
  slot, resource, and saga documentation.
- `src/direttore/core/primitives/primitives_v2.md` — removed because
  `docs/README.md` and `README.md` already own the current `ResourceHolder` and
  UoW contracts.
- `src/direttore/core/resolvers/resolvers.md` — removed because handler
  resolution, caching, validation, and operation-loading behavior are already
  documented in `docs/README.md`.
- `src/direttore/core/modular_monolith_support/uow_routing_registries/uow_routing_registries_v2.md`
  — removed because `docs/modular-monolith.md` already owns the current routing
  and shared-holder model.
- `src/direttore/core/tracing/tracing.md` — removed after its exception
  propagation requirement was preserved in the tracing section of
  `docs/README.md`; lease span ownership remains documented in
  `slot_and_slot_lease.md`.
- `src/direttore/core/saga/README.md` — removed after its journal/resource
  atomicity qualification was preserved in the saga section of
  `docs/README.md`; the rest duplicated that guide.
- `tree.txt` — removed as an ignored, stale generated repository snapshot.
- `filesystem_test/` — confirmed absent; no replacement test artifact was
  created.
- `artifacts/2026-08-15-repository-cleanup-report.md` — this report.

The current durable Markdown homes are intentional: `README.md` is the project
overview, `MIGRATION.md` is the migration guide, `slot_and_slot_lease.md` owns
the focused execution-boundary model, and `docs/README.md`,
`docs/simple-service.md`, `docs/modular-monolith.md`, and
`docs/project-structure.md` are the canonical detailed guides. `AGENTS.md`
contains project instructions, `.agents/skills/final-report/SKILL.md` contains
the reporting workflow, and existing files under `artifacts/` remain historical
completion reports.

## Implementation notes

- No Python implementation or test file was changed by this cleanup.
- The pre-existing worktree updates to `README.md`, removal of the root
  `REFACTOR_REPORT.md`, and relocation/policy files under `.agents/` and
  `artifacts/` were preserved rather than reverted.
- Historical reports still mention `AGENT.md` where that was the factual
  filename at the time; these are historical statements, not live links or
  active project-instruction references.
- The three tracked `.DS_Store` paths are deleted in the working tree and will
  leave the tracked-file index when the cleanup is committed. No files were
  staged or committed by this task.

## Tests and validation

- `find . -name .DS_Store -not -path './.git/*' -not -path './.venv/*'` —
  passed; no working-tree matches.
- `git ls-files --deleted | grep -E '(^|/)\.DS_Store$'` — reported exactly the
  three intended pending deletions: `.DS_Store`, `src/.DS_Store`, and
  `src/direttore/.DS_Store`.
- `git check-ignore -v --stdin` with a nested `.DS_Store` path — passed; the
  new `.gitignore` rule matched.
- Final Markdown inventory — passed; no Markdown remains under `src/`, and no
  root scratch/report file was added.
- Removed-path `rg` search over non-historical Markdown — passed; no stale
  references found.
- Local Markdown link checker — passed; 16 repository-local links resolved.
- `git diff --check` — passed.
- Python implementation diff check — passed; no `*.py` diff.
- `codex exec --ephemeral --sandbox read-only ...` instruction-discovery check
  — passed after granting access to local Codex state; reported `AGENTS.md`.
- `uv run pytest -q` — passed after granting access to the uv cache: 38 tests
  passed.
- `uv run ruff check src tests` — passed after granting access to the uv cache.
- `uv run ruff format --check src tests` — failed: 7 pre-existing Python files
  would be reformatted and 64 files were already formatted. They were not
  reformatted because this task forbids Python changes.
- `uvx pyright src` — passed after granting access to the uv cache: 0 errors,
  0 warnings, 0 informations.
- Initial sandboxed attempts to run the uv-based checks could not read
  `/Users/dmitrijkanevskij/.cache/uv/sdists-v9/.git`; the checks above are the
  actual results from the approved reruns.

## Unresolved items

- The repository has a pre-existing Ruff formatting drift in seven Python
  files. Correcting it is outside this documentation-only cleanup.
- No unresolved documentation ambiguity remains.

## Proposed git commit message

`chore: clean repository documentation and artifacts`
