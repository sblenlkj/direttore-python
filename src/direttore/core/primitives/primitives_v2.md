# Unified ResourceHolder and Unit of Work

`ResourceHolder` is the sole owner of execution-scoped resources for commands,
queries, events, operation loaders, and saga persistence.

## Named lazy resources

Factories are registered by name. A resource is not created until requested:

```python
holder = ResourceHolder(
    {
        "primary": primary_session_factory,
        "analytics": analytics_session_factory,
    }
)
```

`get_session(name, commit=False)` caches the created object. Repeated calls for
one name return the same object. Different names have independent objects and
commit intent.

Commit intent can only increase:

```text
False -> False
False -> True
True  -> True
```

## Finalization

On successful execution, holder commit:

1. commits write-intent resources in creation order;
2. rolls back read-only resources;
3. clears execution-local saga entries.

On failure, rollback visits every opened resource. Close runs in reverse
creation order and clears all cached references so a pooled physical slot can
reuse the holder.

Zero-resource executions do not invoke factories or lifecycle methods on a
resource.

If a write commit fails, `MultiResourceCommitError` reports `committed`,
`failed`, and `not_committed`. Remaining resources receive best-effort rollback.
No automatic compensation or cross-resource recovery is attempted.

> Direttore does not guarantee atomicity across independent resources.

## Unit of Work

`BaseUnitOfWork` is a typed access facade. It owns no second cache:

```python
await uow.read_session("primary")  # commit=False
await uow.write_session("primary")  # commit=True
```

Repositories should retain the holder or UoW and resolve sessions lazily. They
must not retain a session across lease release.
