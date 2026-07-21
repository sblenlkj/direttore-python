from __future__ import annotations

from collections.abc import Callable
from typing import Any

from direttore.core.contracts.handlers import (
    UseCaseHandler,
    UseCaseHandlerConfig,
)
from direttore.core.contracts.messages import UseCaseCommand
from direttore.core.registries.base_handler_registry import (
    BaseHandlerRegistry,
)
from direttore.core.registries.errors import (
    InvalidHandlerTypeError,
    InvalidMessageTypeError,
)
from direttore.core.registries.registrations import (
    UseCaseHandlerRegistration,
)


class UseCaseHandlerRegistry(
    BaseHandlerRegistry[UseCaseHandlerRegistration],
):
    def register(
        self,
        command_type: type[UseCaseCommand],
        handler_type: type[UseCaseHandler],
        *,
        key: str | None = None,
        config: UseCaseHandlerConfig | None = None,
    ) -> None:
        self._validate_command_type(command_type)
        self._validate_handler_type(handler_type)

        registration = UseCaseHandlerRegistration(
            command_type=command_type,
            handler_type=handler_type,
            key=key,
            source_name=self.source_name,
            config=config or UseCaseHandlerConfig(),
        )

        self._add_registration(
            message_type=command_type,
            registration=registration,
            key=key,
        )

    def decorator_register(
        self,
        command_type: type[UseCaseCommand],
        *,
        key: str | None = None,
        config: UseCaseHandlerConfig | None = None,
    ) -> Callable[[type[UseCaseHandler]], type[UseCaseHandler]]:
        def decorator(
            handler_type: type[UseCaseHandler],
        ) -> type[UseCaseHandler]:
            self.register(
                command_type=command_type,
                handler_type=handler_type,
                key=key,
                config=config,
            )

            return handler_type

        return decorator

    def get_handler_type(
        self,
        command_type: type[UseCaseCommand],
    ) -> type[UseCaseHandler]:
        return self.get_registration(command_type).handler_type

    def get_handler_type_by_key(
        self,
        key: str,
    ) -> type[UseCaseHandler]:
        return self.get_registration_by_key(key).handler_type

    def get_config(
        self,
        command_type: type[UseCaseCommand],
    ) -> UseCaseHandlerConfig:
        return self.get_registration(command_type).config

    def _get_message_type(
        self,
        registration: UseCaseHandlerRegistration,
    ) -> type[Any]:
        return registration.command_type

    def _get_handler_type(
        self,
        registration: UseCaseHandlerRegistration,
    ) -> type[Any]:
        return registration.handler_type

    def _get_key(
        self,
        registration: UseCaseHandlerRegistration,
    ) -> str | None:
        return registration.key

    def _validate_command_type(
        self,
        command_type: type[UseCaseCommand],
    ) -> None:
        if issubclass(command_type, UseCaseCommand):
            return

        raise InvalidMessageTypeError(
            f"Expected UseCaseCommand subclass, got "
            f"'{command_type.__module__}.{command_type.__qualname__}'."
        )

    def _validate_handler_type(
        self,
        handler_type: type[UseCaseHandler],
    ) -> None:
        if issubclass(handler_type, UseCaseHandler):
            return

        raise InvalidHandlerTypeError(
            f"Expected UseCaseHandler subclass, got "
            f"'{handler_type.__module__}.{handler_type.__qualname__}'."
        )