# Saga foundation

Saga support records payloads for successful compensable handlers and can run
idempotent compensation in reverse order.

## Data model

- `SagaEntry`: handler kind, stable handler key, serialized payload.
- `SagaRecord`: saga ID and immutable tuple of entries.
- `SagaHandlerResult`: business result plus compensation object.
- `SagaCompensationContext`: saga ID, UoW, lifecycle context, and span.

The saga ID belongs to a normal call or lease. It is not duplicated in every
entry. Queries do not create saga entries.

## Save ordering

Entries accumulate in the unified holder. Lease commit performs:

```text
journal.save(payload-based SagaRecord)
resource-holder commit
clear in-memory entries
```

The in-memory journal deep-copies payloads on save and load to exercise the
same serialization boundary expected from Redis or SQL implementations.

SQL journal persistence can be atomic with business state only when the journal
uses the same session. In-memory/Redis persistence is not atomic with SQL.
With several resources, journal persistence is atomic only relative to the
resource actually used by the journal.

## Compensation

`compensate_saga` loads a record, walks entries in reverse order, resolves by
`SagaHandlerKind` and stable key, calls `from_payload`, and invokes the original
handler's `compensate` method.

Compensation methods must be idempotent. This initial journal API intentionally
does not expose retry attempts, timestamps, step IDs, or public statuses.
