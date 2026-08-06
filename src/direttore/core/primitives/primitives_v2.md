# Unified ResourceHolder and Unit of Work

`ResourceHolder` is the sole owner of execution-scoped resources for commands,
events, operation loaders, and saga persistence.

## Named lazy resources

Factories are registered by name. A resource is not created until requested:

```python
holder = ApplicationResourceHolder(
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

`ResourceHolder` is abstract. Application infrastructure implements
`commit()`, `rollback()`, and `close()`. Implementations call
`_mark_finalized()` after commit or rollback. `close()` closes owned resources;
the execution slot then calls public `reset()` to clear execution-scoped holder
state. Direttore does not prescribe ordering, partial-failure recovery, or
cross-resource atomicity.

## Unit of Work

`BaseUnitOfWork` is a typed access facade. It owns no second cache:

```python
await uow.read_session("primary")  # commit=False
await uow.write_session("primary")  # commit=True
```

Repositories should retain the holder or UoW and resolve sessions lazily. They
must not retain a session across lease release.
