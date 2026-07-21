from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Self

from direttore.core.contracts.handlers import EventHandler
from direttore.core.contracts.messages import Event
from direttore.core.registries.errors import (
    HandlerAlreadyRegisteredError,
    HandlerNotRegisteredError,
    InvalidHandlerTypeError,
    InvalidMessageTypeError,
)
from direttore.core.registries.registrations import (
    EventHandlerRegistration,
)


class EventHandlerRegistry:
    def __init__(
        self,
        source_name: str | None = None,
    ) -> None:
        self.source_name = source_name
        self._registrations_by_event_type: dict[
            type[Event],
            list[EventHandlerRegistration],
        ] = {}

    def register(
        self,
        event_type: type[Event],
        handler_type: type[EventHandler],
        *,
        is_ready: bool = True,
    ) -> None:
        self._validate_event_type(event_type)
        self._validate_handler_type(handler_type)

        registration = EventHandlerRegistration(
            event_type=event_type,
            handler_type=handler_type,
            source_name=self.source_name,
            is_ready=is_ready,
        )

        self._add_registration(
            event_type=event_type,
            registration=registration,
        )

    def decorator_register(
        self,
        event_type: type[Event],
        *,
        is_ready: bool = True,
    ) -> Callable[[type[EventHandler]], type[EventHandler]]:
        def decorator(
            handler_type: type[EventHandler],
        ) -> type[EventHandler]:
            self.register(
                event_type=event_type,
                handler_type=handler_type,
                is_ready=is_ready,
            )

            return handler_type

        return decorator

    def has_handler(
        self,
        event_type: type[Event],
    ) -> bool:
        return bool(self._registrations_by_event_type.get(event_type))

    def get_registrations(
        self,
        event_type: type[Event],
        *,
        ready_only: bool = True,
    ) -> list[EventHandlerRegistration]:
        registrations = self._registrations_by_event_type.get(event_type, [])

        if ready_only:
            registrations = [
                registration
                for registration in registrations
                if registration.is_ready
            ]

        if not registrations:
            raise HandlerNotRegisteredError(
                f"No event handlers registered for event type "
                f"'{event_type.__module__}.{event_type.__qualname__}'."
            )

        return list(registrations)

    def get_handler_types(
        self,
        event_type: type[Event],
        *,
        ready_only: bool = True,
    ) -> list[type[EventHandler]]:
        return [
            registration.handler_type
            for registration in self.get_registrations(
                event_type,
                ready_only=ready_only,
            )
        ]

    def iter_registrations(self) -> Iterable[EventHandlerRegistration]:
        for registrations in self._registrations_by_event_type.values():
            yield from registrations

    def _add_registration(
        self,
        *,
        event_type: type[Event],
        registration: EventHandlerRegistration,
    ) -> None:
        registrations = self._registrations_by_event_type.setdefault(
            event_type,
            [],
        )

        for existing_registration in registrations:
            if existing_registration.handler_type is registration.handler_type:
                raise HandlerAlreadyRegisteredError(
                    f"Handler "
                    f"'{registration.handler_type.__module__}."
                    f"{registration.handler_type.__qualname__}' "
                    f"is already registered for event type "
                    f"'{event_type.__module__}.{event_type.__qualname__}'."
                )

        registrations.append(registration)

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
                    event_type=registration.event_type,
                    registration=registration,
                )

        return merged

    def _validate_event_type(
        self,
        event_type: type[Event],
    ) -> None:
        if issubclass(event_type, Event):
            return

        raise InvalidMessageTypeError(
            f"Expected Event subclass, got "
            f"'{event_type.__module__}.{event_type.__qualname__}'."
        )

    def _validate_handler_type(
        self,
        handler_type: type[EventHandler],
    ) -> None:
        if issubclass(handler_type, EventHandler):
            return

        raise InvalidHandlerTypeError(
            f"Expected EventHandler subclass, got "
            f"'{handler_type.__module__}.{handler_type.__qualname__}'."
        )