from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from inspect import isawaitable
from typing import Any

from direttore.core.saga.models import SagaEntry

type ResourceFactory = Callable[[], Any | Awaitable[Any]]


class ResourceHolderError(Exception):
    """Base error for execution-scoped resource management."""


class ResourceNotRegisteredError(ResourceHolderError):
    pass


class ResourceAlreadyRegisteredError(ResourceHolderError):
    pass


class ResourceClosedError(ResourceHolderError):
    pass


class MultiResourceCommitError(ResourceHolderError):
    """A deterministic best-effort commit failed after a partial commit."""

    def __init__(
        self,
        *,
        committed: list[str],
        failed: str,
        not_committed: list[str],
    ) -> None:
        self.committed = tuple(committed)
        self.failed = failed
        self.not_committed = tuple(not_committed)
        super().__init__(
            "Commit failed for resource "
            f"{failed!r}; committed={committed!r}, "
            f"not_committed={not_committed!r}. Direttore does not "
            "guarantee atomicity across independent resources."
        )


class ResourceHolder:
    """The single owner of lazy named resources for an execution slot.

    A named resource is created on first access and cached until the holder is
    closed. Commit intent is tracked independently per name and is monotonic:
    a later write access upgrades a read resource, while a later read can never
    downgrade a write resource.

    Transaction boundaries are explicit. Slots call :meth:`open`,
    :meth:`commit` or :meth:`rollback`, and :meth:`close`; the holder does not
    decide when an application transaction should end.
    """

    def __init__(
        self,
        factories: Mapping[str, ResourceFactory] | None = None,
    ) -> None:
        self._factories = dict(factories or {})
        self._resources: dict[str, Any] = {}
        self._commit_required: dict[str, bool] = {}
        self._saga_entries: list[SagaEntry] = []
        self._is_open = False
        self._is_finalized = False

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def is_finalized(self) -> bool:
        return self._is_finalized

    @property
    def has_open_resources(self) -> bool:
        return bool(self._resources)

    @property
    def created_resource_names(self) -> tuple[str, ...]:
        return tuple(self._resources)

    @property
    def commit_required(self) -> Mapping[str, bool]:
        return dict(self._commit_required)

    @property
    def saga_entries(self) -> tuple[SagaEntry, ...]:
        return tuple(self._saga_entries)

    def register(
        self,
        name: str,
        factory: ResourceFactory,
        *,
        override: bool = False,
    ) -> None:
        if name in self._factories and not override:
            raise ResourceAlreadyRegisteredError(
                f"Resource {name!r} is already registered."
            )
        if name in self._resources:
            raise ResourceHolderError(
                f"Cannot replace already-created resource {name!r}."
            )
        self._factories[name] = factory

    def has(self, name: str) -> bool:
        return name in self._factories

    def is_created(self, name: str) -> bool:
        return name in self._resources

    async def open(self) -> None:
        if self._is_open:
            raise ResourceHolderError("ResourceHolder is already open.")
        if self._resources:
            raise ResourceHolderError(
                "ResourceHolder still owns resources from a previous scope."
            )
        self._is_open = True
        self._is_finalized = False

    async def get_session(
        self,
        name: str = "primary",
        *,
        commit: bool = False,
    ) -> Any:
        self._ensure_can_use_resources()
        if name in self._resources:
            if commit:
                self._commit_required[name] = True
            return self._resources[name]
        if name not in self._factories:
            raise ResourceNotRegisteredError(f"Resource {name!r} is not registered.")
        resource = self._factories[name]()
        if isawaitable(resource):
            resource = await resource
        self._resources[name] = resource
        self._commit_required[name] = commit
        return resource

    async def get(
        self,
        name: str,
        *,
        commit: bool = False,
    ) -> Any:
        """Return a named resource; retained as the generic accessor."""
        return await self.get_session(name, commit=commit)

    def append_saga_entry(self, entry: SagaEntry) -> None:
        self._ensure_can_use_resources()
        self._saga_entries.append(entry)

    def clear_saga_entries(self) -> None:
        self._saga_entries.clear()

    async def commit(self) -> None:
        """Commit writes, rollback reads, and retain partial-failure details."""
        self._ensure_can_finalize()
        write_names = [name for name in self._resources if self._commit_required[name]]
        read_names = [
            name for name in self._resources if not self._commit_required[name]
        ]
        committed: list[str] = []
        try:
            for index, name in enumerate(write_names):
                try:
                    await self._call_resource(name, "commit")
                except BaseException as exc:
                    await self._rollback_names(write_names[index:])
                    await self._rollback_names(read_names)
                    raise MultiResourceCommitError(
                        committed=committed,
                        failed=name,
                        not_committed=write_names[index + 1 :],
                    ) from exc
                committed.append(name)
            await self._rollback_names(read_names)
            self._is_finalized = True
        finally:
            if self._is_finalized:
                self.clear_saga_entries()

    async def rollback(self) -> None:
        self._ensure_open()
        if self._is_finalized:
            return
        try:
            await self._rollback_names(list(self._resources))
        finally:
            self._is_finalized = True
            self.clear_saga_entries()

    async def close(self) -> None:
        """Close every created resource and make the holder reusable."""
        first_error: BaseException | None = None
        for name in reversed(tuple(self._resources)):
            try:
                await self._call_resource(name, "close")
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        self._resources.clear()
        self._commit_required.clear()
        self._saga_entries.clear()
        self._is_open = False
        self._is_finalized = False
        if first_error is not None:
            raise first_error

    async def __aenter__(self) -> ResourceHolder:
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> bool:
        try:
            if exc_type is None:
                await self.commit()
            else:
                await self.rollback()
        finally:
            await self.close()
        return False

    async def _rollback_names(self, names: list[str]) -> None:
        first_error: BaseException | None = None
        for name in names:
            try:
                await self._call_resource(name, "rollback")
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error

    async def _call_resource(self, name: str, method_name: str) -> None:
        method = getattr(self._resources[name], method_name, None)
        if method is None:
            return
        result = method()
        if isawaitable(result):
            await result

    def _ensure_open(self) -> None:
        if not self._is_open:
            raise ResourceClosedError("ResourceHolder is not open.")

    def _ensure_can_finalize(self) -> None:
        self._ensure_open()
        if self._is_finalized:
            raise ResourceHolderError(
                "ResourceHolder transaction is already finalized."
            )

    def _ensure_can_use_resources(self) -> None:
        self._ensure_open()
        if self._is_finalized:
            raise ResourceClosedError(
                "ResourceHolder transaction is already finalized."
            )


# A neutral compatibility name for code that previously depended on the base
# holder without choosing read-side or write-side ownership.
BaseResourceHolder = ResourceHolder
