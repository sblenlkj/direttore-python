# Direttore architecture guide

Direttore is a Python 3.12 slot-centric orchestration framework.

## Ownership

Physical execution slots own the complete execution scope:

- direct/key/operation message resolution and payload construction;
- lifecycle-context creation and cleanup;
- root and child tracing spans;
- the unified `ResourceHolder` and UoW access;
- event queue and transaction-relative event timing;
- saga entry collection, persistence, and compensation;
- commit, rollback, close, and reusable-slot reset.

Do not add orchestration engines back. Shared code may be extracted only when it
retains a concrete responsibility and does not create a second execution path.

`BaseExecutionSlot[InputT, TraceT]` owns the plain-slot use-case pipeline:
message construction, lifecycle creation, handler invocation, saga collection,
transaction-relative event timing, tracing, commit, and cleanup. `SlotLease`
owns its separate non-committing invocation path and defers one commit across
sequential operations. Concrete simple and modular slots implement resolver
lookup, UoW selection, event dispatch, compensation routing, and modular
execution-context state.

## Slot and lease

`BaseExecutionSlot` is a reusable physical container owned by a provider.
`SlotLease` is temporary generation-checked ownership. Automatic application
methods use their facade's `transactional_slot()` boundary to acquire a
physical slot, invoke it, roll back failures, and release it. A plain physical
slot commits inside its use-case invocation so post-commit events can drain
before the operation span closes.
Explicit transactional islands acquire a lease and use its six methods.
Only the lease/list owns lifecycle/span cache state. Physical execution-slot
modules contain no cache type, cache parameter, or cache execution branch.
`SlotLease` calls the typed base-slot contract directly; do not restore dynamic
attribute access or `type: ignore` dispatch.

One lease is sequential. Concurrent use is a framework error. A failed handler
leaves it active. Release rolls back uncommitted work directly. A released or
stale lease must never reach a reused slot.

## Resources and UoW

Use only `ResourceHolder`. Do not add message-specific holders. Named resources
are lazy and cached. Commit intent is monotonic per name. The UoW delegates
reads and writes to the holder and owns no cache or transaction state.

`ResourceHolder` is abstract. Concrete application holders implement commit,
rollback, and close policy, call `_mark_finalized()` after finalization, and
leave state reset to the execution slot after resources are closed. Never imply
transaction guarantees that the concrete holder does not implement.

## Events

For plain slots, `IN_TRANSACTION` drains events before commit, while
`AFTER_TRANSACTION` commits business resources first and opens a new resource
boundary for events. `SlotLease` drains every operation's events immediately,
regardless of transaction-relative execution mode, and still defers its single
resource commit. Event dispatchers resolve/invoke handlers but never own the
top-level transaction.

## Modular monolith

The coordinator receives one unified holder. Its use-case UoWs delegate to that
holder. Runtime nested invocations receive lifecycle state for the active
operation and explicit parent spans. Never store an active span in the runtime.

## Saga

Saga keys and compensation types are registration metadata. Commands and
events do not carry handler keys. Use `SagaUseCaseHandlerResult` for use cases
and `SagaEventHandlerResult` for events. Store only payload-based `SagaEntry`
values in the holder and journal. Persist before commit. Compensate in reverse
order and require idempotent compensation methods.

Do not add nested sagas, distributed locks, two-phase commit, a retry daemon,
or durable slot storage without a separate architecture change.

## Agent integration

Pass `SlotLease` only through transient agent runtime/context. Never serialize
it into graph state. Use a transactional subgraph so graph checkpoints cannot
claim an internal DB node completed while its encompassing transaction later
rolls back.

## Change checklist

1. Inspect both application variants and public exports.
2. Preserve both typed application facades and the explicit lease pipeline.
3. Add focused tests for ownership, failure, cleanup, and ordering.
4. Update `__init__.py` exports and durable documentation only when the public API or documented behavior actually changes; do not create migration/report files merely because a task completed.
5. Run pytest, Ruff format/lint, Pyright, and stale-reference searches.

## Completion reports

For every completed repository task that changed code, tests, documentation, examples, benchmarks, or project structure, use the repository skill at `.agents/skills/final-report/SKILL.md` for the final handoff report.

Completion reports belong only under `artifacts/` and use the filename form `YYYY-MM-DD-<task-slug>-report.md`. Do not create task-specific refactor, migration, benchmark, or completion-report Markdown files in the repository root. Existing durable documents such as `MIGRATION.md`, `README.md`, and files under `docs/` are updated only when their actual subject matter changes.
