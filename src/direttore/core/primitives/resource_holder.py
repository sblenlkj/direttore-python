from __future__ import annotations

from abc import ABC, abstractmethod
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


class ResourceFinalizedError(ResourceHolderError):
    pass


class ResourceHolder(ABC):
    """Base holder for lazy named execution resources.

    The holder owns resource factories, lazy resource creation, resource
    caching, monotonic commit intent, the active saga ID, and execution-local
    saga entries. Concrete holders implement transaction finalization.
    """

    def __init__(
        self,
        factories: Mapping[str, ResourceFactory] | None = None,
    ) -> None:
        self._factories = dict(factories or {})
        self._resources: dict[str, Any] = {}
        self._commit_required: dict[str, bool] = {}
        self._saga_entries: list[SagaEntry] = []
        self.saga_id: str | None = None
        self._is_finalized = False

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

    async def get_session(
        self,
        name: str = "primary",
        *,
        commit: bool = False,
    ) -> Any:
        self._ensure_not_finalized()
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
        return await self.get_session(name, commit=commit)

    def append_saga_entry(self, entry: SagaEntry) -> None:
        self._ensure_not_finalized()
        self._saga_entries.append(entry)

    def clear_saga_entries(self) -> None:
        self._saga_entries.clear()

    @abstractmethod
    async def commit(self) -> None:
        """Finalize the holder successfully."""
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        """Rollback resources owned by the holder."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close resources owned by the holder."""
        raise NotImplementedError

    def _mark_finalized(self) -> None:
        self._is_finalized = True
        self.clear_saga_entries()

    def reset(self) -> None:
        """Clear execution-scoped state after resources have been closed."""
        self._resources.clear()
        self._commit_required.clear()
        self._saga_entries.clear()
        self.saga_id = None
        self._is_finalized = False

    def _ensure_not_finalized(self) -> None:
        if self._is_finalized:
            raise ResourceFinalizedError(
                "ResourceHolder transaction is already finalized."
            )
