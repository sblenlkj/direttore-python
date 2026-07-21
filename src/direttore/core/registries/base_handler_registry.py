from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any, Self

from direttore.core.registries.errors import (
    HandlerAlreadyRegisteredError,
    HandlerKeyAlreadyRegisteredError,
    HandlerKeyNotRegisteredError,
    HandlerNotRegisteredError,
)


class BaseHandlerRegistry[RegistrationT](ABC):
    def __init__(
        self,
        source_name: str | None = None,
    ) -> None:
        self.source_name = source_name
        self._registrations_by_message_type: dict[type[Any], RegistrationT] = {}
        self._registrations_by_key: dict[str, RegistrationT] = {}

    def has_handler(
        self,
        message_type: type[Any],
    ) -> bool:
        return message_type in self._registrations_by_message_type

    def has_key(
        self,
        key: str,
    ) -> bool:
        return key in self._registrations_by_key

    def get_registration(
        self,
        message_type: type[Any],
    ) -> RegistrationT:
        registration = self._registrations_by_message_type.get(message_type)

        if registration is None:
            raise HandlerNotRegisteredError(
                f"No handler registered for message type "
                f"'{message_type.__module__}.{message_type.__qualname__}'."
            )

        return registration

    def get_registration_by_key(
        self,
        key: str,
    ) -> RegistrationT:
        registration = self._registrations_by_key.get(key)

        if registration is None:
            raise HandlerKeyNotRegisteredError(
                f"No handler registered for key '{key}'."
            )

        return registration

    def iter_registrations(self) -> Iterable[RegistrationT]:
        return self._registrations_by_message_type.values()

    def _add_registration(
        self,
        *,
        message_type: type[Any],
        registration: RegistrationT,
        key: str | None,
    ) -> None:
        if message_type in self._registrations_by_message_type:
            raise HandlerAlreadyRegisteredError(
                f"Handler already registered for message type "
                f"'{message_type.__module__}.{message_type.__qualname__}'."
            )

        if key is not None and key in self._registrations_by_key:
            raise HandlerKeyAlreadyRegisteredError(
                f"Handler key '{key}' is already registered."
            )

        self._registrations_by_message_type[message_type] = registration

        if key is not None:
            self._registrations_by_key[key] = registration

    @classmethod
    def merge_many(
        cls,
        registries: Iterable[Self],
        *,
        source_name: str | None = None,
    ) -> Self:
        merged = cls(source_name=source_name)

        for registry in registries:
            for registration in registry.iter_registrations():
                merged._add_registration(
                    message_type=registry._get_message_type(registration),
                    registration=registration,
                    key=registry._get_key(registration),
                )

        return merged

    @abstractmethod
    def _get_message_type(
        self,
        registration: RegistrationT,
    ) -> type[Any]:
        raise NotImplementedError

    @abstractmethod
    def _get_handler_type(
        self,
        registration: RegistrationT,
    ) -> type[Any]:
        raise NotImplementedError

    @abstractmethod
    def _get_key(
        self,
        registration: RegistrationT,
    ) -> str | None:
        raise NotImplementedError