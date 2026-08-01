from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from direttore.core.primitives.uow import BaseUnitOfWork


class UowRoutingRegistryError(Exception):
    pass


class UowRouteAlreadyRegisteredError(UowRoutingRegistryError):
    pass


class UowRouteNotRegisteredError(UowRoutingRegistryError):
    pass


class InvalidUnitOfWorkTypeError(UowRoutingRegistryError):
    pass


@dataclass(frozen=True, slots=True)
class UowRoutingRegistryItem[RegistryT]:
    registry: RegistryT
    root_uow_type: type[BaseUnitOfWork]


class BaseUowRoutingRegistry:
    def __init__(self) -> None:
        self._uow_types_by_handler_type: dict[
            type[Any],
            type[BaseUnitOfWork],
        ] = {}

    def register(
        self,
        *,
        handler_type: type[Any],
        root_uow_type: type[BaseUnitOfWork],
    ) -> None:
        self._validate_handler_type(handler_type)
        self._validate_uow_type(root_uow_type)

        existing_uow_type = self._uow_types_by_handler_type.get(handler_type)

        if existing_uow_type is not None:
            if existing_uow_type is root_uow_type:
                return

            raise UowRouteAlreadyRegisteredError(
                "UoW route already registered for handler type "
                f"'{handler_type.__module__}.{handler_type.__qualname__}'. "
                f"Existing UoW="
                f"'{existing_uow_type.__module__}."
                f"{existing_uow_type.__qualname__}', "
                f"new UoW="
                f"'{root_uow_type.__module__}."
                f"{root_uow_type.__qualname__}'."
            )

        self._uow_types_by_handler_type[handler_type] = root_uow_type

    def has_uow_type_by_handler_type(
        self,
        handler_type: type[Any],
    ) -> bool:
        return handler_type in self._uow_types_by_handler_type

    def get_uow_type_by_handler_type(
        self,
        handler_type: type[Any],
    ) -> type[BaseUnitOfWork]:
        root_uow_type = self._uow_types_by_handler_type.get(handler_type)

        if root_uow_type is None:
            raise UowRouteNotRegisteredError(
                "No UoW route registered for handler type "
                f"'{handler_type.__module__}.{handler_type.__qualname__}'."
            )

        return root_uow_type

    def iter_routes(
        self,
    ) -> Iterable[tuple[type[Any], type[BaseUnitOfWork]]]:
        return self._uow_types_by_handler_type.items()

    def _validate_handler_type(
        self,
        handler_type: type[Any],
    ) -> None:
        if isinstance(handler_type, type):
            return

        raise TypeError(f"Handler type must be a type, got {handler_type!r}.")

    def _validate_uow_type(
        self,
        root_uow_type: type[BaseUnitOfWork],
    ) -> None:
        if not isinstance(root_uow_type, type):
            raise InvalidUnitOfWorkTypeError(
                f"Unit of Work type must be a type, got {root_uow_type!r}."
            )

        if issubclass(root_uow_type, BaseUnitOfWork):
            return

        raise InvalidUnitOfWorkTypeError(
            f"Expected BaseUnitOfWork subclass, got "
            f"'{root_uow_type.__module__}.{root_uow_type.__qualname__}'."
        )
