from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Self

from direttore.core.contracts.handlers import (
    QueryHandler,
    QueryHandlerConfig,
)
from direttore.core.contracts.lifecycle import (
    DefaultQueryLifecycle,
    QueryLifecycle,
)
from direttore.core.contracts.messages import Query
from direttore.core.registries.errors import (
    HandlerAlreadyRegisteredError,
    HandlerKeyAlreadyRegisteredError,
    HandlerKeyNotRegisteredError,
    HandlerNotRegisteredError,
    InvalidHandlerTypeError,
    InvalidMessageTypeError,
)
from direttore.core.registries.registrations import (
    QueryHandlerRegistration,
)


class QueryHandlerRegistry:
    def __init__(
        self,
        source_name: str | None = None,
        *,
        default_lifecycle: QueryLifecycle | None = None,
        default_config: QueryHandlerConfig | None = None,
    ) -> None:
        self.source_name = source_name
        self.default_lifecycle = (
            default_lifecycle
            if default_lifecycle is not None
            else DefaultQueryLifecycle()
        )
        self.default_config = (
            default_config
            if default_config is not None
            else QueryHandlerConfig()
        )

        self._registrations_by_query_type: dict[
            type[Query],
            QueryHandlerRegistration,
        ] = {}
        self._registrations_by_key: dict[
            str,
            QueryHandlerRegistration,
        ] = {}

    def register(
        self,
        query_type: type[Query],
        handler_type: type[QueryHandler],
        *,
        key: str | None = None,
        config: QueryHandlerConfig | None = None,
        lifecycle: QueryLifecycle | None = None,
    ) -> None:
        self._validate_query_type(query_type)
        self._validate_handler_type(handler_type)

        registration = QueryHandlerRegistration(
            query_type=query_type,
            handler_type=handler_type,
            key=key,
            source_name=self.source_name,
            config=config if config is not None else self.default_config,
            lifecycle=(
                lifecycle
                if lifecycle is not None
                else self.default_lifecycle
            ),
        )

        self._add_registration(registration)

    def decorator_register(
        self,
        query_type: type[Query],
        *,
        key: str | None = None,
        config: QueryHandlerConfig | None = None,
        lifecycle: QueryLifecycle | None = None,
    ) -> Callable[[type[QueryHandler]], type[QueryHandler]]:
        def decorator(
            handler_type: type[QueryHandler],
        ) -> type[QueryHandler]:
            self.register(
                query_type=query_type,
                handler_type=handler_type,
                key=key,
                config=config,
                lifecycle=lifecycle,
            )

            return handler_type

        return decorator

    def has_handler(
        self,
        query_type: type[Query],
    ) -> bool:
        return query_type in self._registrations_by_query_type

    def has_key(
        self,
        key: str,
    ) -> bool:
        return key in self._registrations_by_key

    def get_registration(
        self,
        query_type: type[Query],
    ) -> QueryHandlerRegistration:
        registration = self._registrations_by_query_type.get(query_type)

        if registration is None:
            raise HandlerNotRegisteredError(
                f"No handler registered for query type "
                f"'{query_type.__module__}.{query_type.__qualname__}'."
            )

        return registration

    def get_registration_by_key(
        self,
        key: str,
    ) -> QueryHandlerRegistration:
        registration = self._registrations_by_key.get(key)

        if registration is None:
            raise HandlerKeyNotRegisteredError(
                f"No query handler registered for key '{key}'."
            )

        return registration

    def get_handler_type(
        self,
        query_type: type[Query],
    ) -> type[QueryHandler]:
        return self.get_registration(query_type).handler_type

    def get_handler_type_by_key(
        self,
        key: str,
    ) -> type[QueryHandler]:
        return self.get_registration_by_key(key).handler_type

    def get_config(
        self,
        query_type: type[Query],
    ) -> QueryHandlerConfig:
        return self.get_registration(query_type).config

    def get_lifecycle(
        self,
        query_type: type[Query],
    ) -> QueryLifecycle:
        return self.get_registration(query_type).lifecycle

    def iter_registrations(
        self,
    ) -> Iterable[QueryHandlerRegistration]:
        return self._registrations_by_query_type.values()

    def _add_registration(
        self,
        registration: QueryHandlerRegistration,
    ) -> None:
        query_type = registration.query_type
        key = registration.key

        if query_type in self._registrations_by_query_type:
            raise HandlerAlreadyRegisteredError(
                f"Handler already registered for query type "
                f"'{query_type.__module__}.{query_type.__qualname__}'."
            )

        if key is not None and key in self._registrations_by_key:
            raise HandlerKeyAlreadyRegisteredError(
                f"Query handler key '{key}' is already registered."
            )

        self._registrations_by_query_type[query_type] = registration

        if key is not None:
            self._registrations_by_key[key] = registration

    @classmethod
    def merge_many(
        cls,
        registries: Iterable[Self],
        *,
        source_name: str | None = None,
        default_lifecycle: QueryLifecycle | None = None,
        default_config: QueryHandlerConfig | None = None,
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

    def _validate_query_type(
        self,
        query_type: type[Query],
    ) -> None:
        if issubclass(query_type, Query):
            return

        raise InvalidMessageTypeError(
            f"Expected Query subclass, got "
            f"'{query_type.__module__}.{query_type.__qualname__}'."
        )

    def _validate_handler_type(
        self,
        handler_type: type[QueryHandler],
    ) -> None:
        if issubclass(handler_type, QueryHandler):
            return

        raise InvalidHandlerTypeError(
            f"Expected QueryHandler subclass, got "
            f"'{handler_type.__module__}.{handler_type.__qualname__}'."
        )