from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import cast

from direttore.core.primitives.resource_holder import (
    AbstractUseCaseResourceHolder,
    QueryResourceHolder,
)
from direttore.core.primitives.uow import BaseUnitOfWork


class ModularUnitOfWorkCoordinator(ABC):
    """Slot-owned Unit of Work coordinator for modular monolith execution.

    The coordinator is a framework base class with an application-specific
    registration hook.

    The framework owns the storage and lookup mechanics:

        UoW type -> UoW instance

    The application owns the concrete UoW list:

        OrdersUseCaseUnitOfWork
        BillingUseCaseUnitOfWork
        CatalogQueryUnitOfWork
        ...

    A coordinator instance belongs to one execution slot. It is created together
    with slot-owned resource holders and keeps long-lived UoW objects for that
    slot. Resource cleanup is handled by ResourceHolder, not by the coordinator.
    """

    def __init__(
        self,
        *,
        use_case_resource_holder: AbstractUseCaseResourceHolder,
        query_resource_holder: QueryResourceHolder | None = None,
    ) -> None:
        self.use_case_resource_holder = use_case_resource_holder
        self.query_resource_holder = query_resource_holder

        self._use_case_uows: dict[
            type[BaseUnitOfWork],
            BaseUnitOfWork,
        ] = {}
        self._query_uows: dict[
            type[BaseUnitOfWork],
            BaseUnitOfWork,
        ] = {}

        self.register()

    @abstractmethod
    def register(self) -> None:
        """Register application-specific Unit of Work objects.

        Implement this method in the application coordinator.

        Example:

            self.register_use_case_uow(
                OrdersUseCaseUnitOfWork(
                    resources=self.use_case_resource_holder,
                )
            )

            self.register_query_uow(
                OrdersQueryUnitOfWork(
                    resources=self.query_resource_holder,
                )
            )

        The framework cannot do this automatically because only the application
        knows which bounded contexts and Unit of Work classes exist.
        """

        raise NotImplementedError

    def register_use_case_uow[UnitOfWorkT: BaseUnitOfWork](
        self,
        uow: UnitOfWorkT,
    ) -> UnitOfWorkT:
        uow_type = type(uow)
        self._validate_uow_type(uow_type)

        if uow_type in self._use_case_uows:
            raise ValueError(
                "Use case unit-of-work is already registered. "
                f"UoW={uow_type.__module__}.{uow_type.__qualname__}."
            )

        self._use_case_uows[uow_type] = uow

        return uow

    def register_query_uow[UnitOfWorkT: BaseUnitOfWork](
        self,
        uow: UnitOfWorkT,
    ) -> UnitOfWorkT:
        uow_type = type(uow)
        self._validate_uow_type(uow_type)

        if uow_type in self._query_uows:
            raise ValueError(
                "Query unit-of-work is already registered. "
                f"UoW={uow_type.__module__}.{uow_type.__qualname__}."
            )

        self._query_uows[uow_type] = uow

        return uow

    def get_use_case_uow[UnitOfWorkT: BaseUnitOfWork](
        self,
        uow_type: type[UnitOfWorkT],
    ) -> UnitOfWorkT:
        self._validate_uow_type(uow_type)

        uow = self._use_case_uows.get(uow_type)

        if uow is None:
            raise LookupError(
                "Use case unit-of-work is not registered. "
                f"UoW={uow_type.__module__}.{uow_type.__qualname__}."
            )

        return cast(UnitOfWorkT, uow)

    def get_query_uow[UnitOfWorkT: BaseUnitOfWork](
        self,
        uow_type: type[UnitOfWorkT],
    ) -> UnitOfWorkT:
        self._validate_uow_type(uow_type)

        uow = self._query_uows.get(uow_type)

        if uow is None:
            raise LookupError(
                "Query unit-of-work is not registered. "
                f"UoW={uow_type.__module__}.{uow_type.__qualname__}."
            )

        return cast(UnitOfWorkT, uow)

    def iter_use_case_unit_of_works(self) -> Iterable[BaseUnitOfWork]:
        return self._use_case_uows.values()

    def iter_query_unit_of_works(self) -> Iterable[BaseUnitOfWork]:
        return self._query_uows.values()

    def iter_unit_of_works(self) -> Iterable[BaseUnitOfWork]:
        yield from self._use_case_uows.values()
        yield from self._query_uows.values()

    def reset(self) -> None:
        """Reset coordinator execution state.

        The default implementation does not delete UoW objects.

        UoW objects are slot-owned and should live together with the slot.
        Execution resources inside them should be reset through ResourceHolder.
        """

    def _validate_uow_type(
        self,
        uow_type: type[BaseUnitOfWork],
    ) -> None:
        if not isinstance(uow_type, type):
            raise TypeError(
                f"Unit of Work type must be a type, got {uow_type!r}."
            )

        if not issubclass(uow_type, BaseUnitOfWork):
            raise TypeError(
                f"{uow_type.__module__}.{uow_type.__qualname__} "
                "must inherit from BaseUnitOfWork."
            )