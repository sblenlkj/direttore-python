from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from inspect import isawaitable
from typing import Any


type ResourceFactory = Callable[[], Any | Awaitable[Any]]


class ResourceHolderError(Exception):
    pass


class ResourceNotRegisteredError(ResourceHolderError):
    pass


class ResourceAlreadyRegisteredError(ResourceHolderError):
    pass


class ResourceClosedError(ResourceHolderError):
    pass


@dataclass()
class BaseResourceHolder:
    """Base execution-scoped lazy resource holder.

    The holder owns resources created during one execution scope.

    It starts without created resources. A resource is created only when `get()`
    is called for its name. Repeated calls return the same resource instance.

    Subclasses may override `close_all()` to close created resources explicitly.
    The framework calls `_close_all()` on exit, which always runs `close_all()`
    first and then clears internal resource references.
    """

    _factories: dict[str, ResourceFactory] = field(default_factory=dict)
    _resources: dict[str, Any] = field(default_factory=dict)

    def register(
        self,
        name: str,
        factory: ResourceFactory,
        *,
        override: bool = False,
    ) -> None:
        if name in self._factories and not override:
            raise ResourceAlreadyRegisteredError(
                f"Resource '{name}' is already registered."
            )

        self._factories[name] = factory

    def has(self, name: str) -> bool:
        return name in self._factories

    def is_created(self, name: str) -> bool:
        return name in self._resources

    async def get(self, name: str) -> Any:
        if name in self._resources:
            return self._resources[name]

        if name not in self._factories:
            raise ResourceNotRegisteredError(
                f"Resource '{name}' is not registered."
            )

        resource = self._factories[name]()

        if isawaitable(resource):
            resource = await resource

        self._resources[name] = resource

        return resource

    async def close_all(self) -> None:
        """Override this hook to close created resources.

        The default implementation does nothing. The framework clears internal
        resource references after this hook finishes.

        Example:

            async def close_all(self) -> None:
                if self.is_created("main_db"):
                    session = await self.get("main_db")
                    await session.close()

                if self.is_created("redis"):
                    redis = await self.get("redis")
                    await redis.aclose()
        """

        return None

    async def _close_all(self) -> None:
        await self.close_all()
        self._resources.clear()


@dataclass()
class QueryResourceHolder(BaseResourceHolder):
    """Read-side execution-scoped resource holder.

    Query execution does not commit or rollback resources.

    It still supports explicit cleanup through `close_all()`. Subclass and
    override `close_all()` when query resources need to be closed explicitly.
    """

    async def __aenter__(self) -> QueryResourceHolder:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> bool:
        await self._close_all()
        return False


@dataclass()
class AbstractUseCaseResourceHolder(BaseResourceHolder, ABC):
    """Write-side execution-scoped resource holder.

    The framework owns the async context manager protocol.

    On successful execution, `__aexit__` calls `commit()`.
    On failed execution, `__aexit__` calls `rollback()`.
    In both cases, `__aexit__` then closes resources through `_close_all()`.

    Concrete implementations must define `commit()` and `rollback()`.

    `commit()` and `rollback()` should only touch resources that were actually
    created during execution. Use `is_created(name)` before calling `get(name)`,
    otherwise a resource may be created only to be committed or rolled back.

    `close_all()` may be overridden when resources need explicit cleanup. The
    framework always clears internal resource references after `close_all()`
    finishes, so user code should not clear holder state manually.

    After the use case execution scope exits, the holder is closed. Any attempt
    to access resources through `get()` will fail fast with `ResourceClosedError`.
    This protects out-of-transaction event handlers from accidentally touching
    transactional resources.

    Example:

        async def commit(self) -> None:
            if self.is_created("main_db"):
                session = await self.get("main_db")
                await session.commit()

        async def rollback(self) -> None:
            if self.is_created("main_db"):
                session = await self.get("main_db")
                await session.rollback()

        async def close_all(self) -> None:
            if self.is_created("main_db"):
                session = await self.get("main_db")
                await session.close()
    """

    _is_open: bool = False

    async def __aenter__(self) -> AbstractUseCaseResourceHolder:
        self._is_open = True
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
            await self._close_all()
            self._is_open = False

        return False

    async def get(self, name: str) -> Any:
        self._ensure_open()
        return await super().get(name)

    def _ensure_open(self) -> None:
        if self._is_open:
            return

        raise ResourceClosedError(
            "UseCaseResourceHolder is closed. "
            "You are trying to access execution-scoped resources after the "
            "use case execution scope has already finished. "
            "This usually means that an event handler is running outside the "
            "transactional phase but still tries to access transactional "
            "resources through UnitOfWork / ResourceHolder."
        )

    @abstractmethod
    async def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        raise NotImplementedError