from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Self

from direttore.core.contracts.handlers import (
    UseCaseEventDrainingMode,
    UseCaseHandler,
    UseCaseHandlerConfig,
    UseCaseHandlerExecutionMode,
)
from direttore.core.contracts.lifecycle import Lifecycle
from direttore.core.contracts.messages import (
    UseCaseCommand,
    UseCaseCommandCompensation,
)
from direttore.core.registries.errors import (
    HandlerAlreadyRegisteredError,
    HandlerKeyAlreadyRegisteredError,
    HandlerKeyNotRegisteredError,
    HandlerNotRegisteredError,
    InvalidHandlerTypeError,
    InvalidMessageTypeError,
)
from direttore.core.registries.registrations import UseCaseHandlerRegistration


class UseCaseHandlerRegistry[LifecycleT: Lifecycle[Any, Any]]:
    def __init__(
        self,
        source_name: str | None = None,
        *,
        default_lifecycle: LifecycleT | None = None,
        default_config: UseCaseHandlerConfig | None = None,
    ) -> None:
        self.source_name = source_name
        self.default_lifecycle = default_lifecycle
        self.default_config = (
            default_config if default_config is not None else UseCaseHandlerConfig()
        )

        self._registrations_by_command_type: dict[
            type[UseCaseCommand],
            UseCaseHandlerRegistration[LifecycleT],
        ] = {}
        self._registrations_by_key: dict[
            str,
            UseCaseHandlerRegistration[LifecycleT],
        ] = {}
        self._registrations_by_saga_key: dict[
            str,
            UseCaseHandlerRegistration[LifecycleT],
        ] = {}

    def register(
        self,
        command_type: type[UseCaseCommand],
        handler_type: type[UseCaseHandler],
        *,
        key: str | None = None,
        saga_key: str | None = None,
        compensation_type: type[UseCaseCommandCompensation] | None = None,
        config: UseCaseHandlerConfig | None = None,
        lifecycle: LifecycleT | None = None,
        execution_mode: UseCaseHandlerExecutionMode = (
            UseCaseHandlerExecutionMode.IN_TRANSACTION
        ),
        event_draining_mode: UseCaseEventDrainingMode = (
            UseCaseEventDrainingMode.SEQUENTIAL
        ),
    ) -> None:
        self._validate_command_type(command_type)
        self._validate_handler_type(handler_type)
        self._validate_saga_metadata(saga_key, compensation_type)

        registration = UseCaseHandlerRegistration(
            command_type=command_type,
            handler_type=handler_type,
            key=key,
            saga_key=saga_key,
            compensation_type=compensation_type,
            source_name=self.source_name,
            config=config if config is not None else self.default_config,
            lifecycle=(lifecycle if lifecycle is not None else self.default_lifecycle),
            execution_mode=execution_mode,
            event_draining_mode=event_draining_mode,
        )

        self._add_registration(registration)

    def decorator_register(
        self,
        command_type: type[UseCaseCommand],
        *,
        key: str | None = None,
        saga_key: str | None = None,
        compensation_type: type[UseCaseCommandCompensation] | None = None,
        config: UseCaseHandlerConfig | None = None,
        lifecycle: LifecycleT | None = None,
        execution_mode: UseCaseHandlerExecutionMode = (
            UseCaseHandlerExecutionMode.IN_TRANSACTION
        ),
        event_draining_mode: UseCaseEventDrainingMode = (
            UseCaseEventDrainingMode.SEQUENTIAL
        ),
    ) -> Callable[[type[UseCaseHandler]], type[UseCaseHandler]]:
        def decorator(
            handler_type: type[UseCaseHandler],
        ) -> type[UseCaseHandler]:
            self.register(
                command_type=command_type,
                handler_type=handler_type,
                key=key,
                saga_key=saga_key,
                compensation_type=compensation_type,
                config=config,
                lifecycle=lifecycle,
                execution_mode=execution_mode,
                event_draining_mode=event_draining_mode,
            )

            return handler_type

        return decorator

    def has_handler(
        self,
        command_type: type[UseCaseCommand],
    ) -> bool:
        return command_type in self._registrations_by_command_type

    def has_key(
        self,
        key: str,
    ) -> bool:
        return key in self._registrations_by_key

    def has_saga_key(
        self,
        saga_key: str,
    ) -> bool:
        return saga_key in self._registrations_by_saga_key

    def get_registration(
        self,
        command_type: type[UseCaseCommand],
    ) -> UseCaseHandlerRegistration[LifecycleT]:
        registration = self._registrations_by_command_type.get(command_type)

        if registration is None:
            raise HandlerNotRegisteredError(
                f"No handler registered for command type "
                f"'{command_type.__module__}.{command_type.__qualname__}'."
            )

        return registration

    def get_registration_by_key(
        self,
        key: str,
    ) -> UseCaseHandlerRegistration[LifecycleT]:
        registration = self._registrations_by_key.get(key)

        if registration is None:
            raise HandlerKeyNotRegisteredError(
                f"No use-case handler registered for key '{key}'."
            )

        return registration

    def get_registration_by_saga_key(
        self,
        saga_key: str,
    ) -> UseCaseHandlerRegistration[LifecycleT]:
        registration = self._registrations_by_saga_key.get(saga_key)

        if registration is None:
            raise HandlerKeyNotRegisteredError(
                f"No use-case handler registered for saga key '{saga_key}'."
            )

        return registration

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

    def get_handler_type_by_saga_key(
        self,
        saga_key: str,
    ) -> type[UseCaseHandler]:
        return self.get_registration_by_saga_key(saga_key).handler_type

    def get_config(
        self,
        command_type: type[UseCaseCommand],
    ) -> UseCaseHandlerConfig:
        return self.get_registration(command_type).config

    def get_lifecycle(
        self,
        command_type: type[UseCaseCommand],
    ) -> LifecycleT | None:
        return self.get_registration(command_type).lifecycle

    def get_execution_mode(
        self,
        command_type: type[UseCaseCommand],
    ) -> UseCaseHandlerExecutionMode:
        return self.get_registration(command_type).execution_mode

    def iter_registrations(
        self,
    ) -> Iterable[UseCaseHandlerRegistration[LifecycleT]]:
        return self._registrations_by_command_type.values()

    def _add_registration(
        self,
        registration: UseCaseHandlerRegistration[LifecycleT],
    ) -> None:
        command_type = registration.command_type
        key = registration.key
        saga_key = registration.saga_key

        if command_type in self._registrations_by_command_type:
            raise HandlerAlreadyRegisteredError(
                f"Handler already registered for command type "
                f"'{command_type.__module__}.{command_type.__qualname__}'."
            )

        if key is not None and key in self._registrations_by_key:
            raise HandlerKeyAlreadyRegisteredError(
                f"Use-case handler key '{key}' is already registered."
            )

        if saga_key is not None and saga_key in self._registrations_by_saga_key:
            raise HandlerKeyAlreadyRegisteredError(
                f"Use-case handler saga key '{saga_key}' is already registered."
            )

        self._registrations_by_command_type[command_type] = registration

        if key is not None:
            self._registrations_by_key[key] = registration

        if saga_key is not None:
            self._registrations_by_saga_key[saga_key] = registration

    @classmethod
    def merge_many(
        cls,
        registries: Iterable[Self],
        *,
        source_name: str | None = None,
        default_lifecycle: LifecycleT | None = None,
        default_config: UseCaseHandlerConfig | None = None,
    ) -> Self:
        merged = cls(
            source_name=source_name,
            default_lifecycle=default_lifecycle,
            default_config=default_config,
        )

        for registry in registries:
            for registration in registry.iter_registrations():
                merged._add_registration(registration)

        return merged

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

    @staticmethod
    def _validate_saga_metadata(
        saga_key: str | None,
        compensation_type: type[UseCaseCommandCompensation] | None,
    ) -> None:
        if (saga_key is None) != (compensation_type is None):
            raise ValueError(
                "saga_key and compensation_type must be provided together."
            )
        if compensation_type is not None and not issubclass(
            compensation_type, UseCaseCommandCompensation
        ):
            raise InvalidMessageTypeError(
                "Use-case compensation type must inherit UseCaseCommandCompensation."
            )
