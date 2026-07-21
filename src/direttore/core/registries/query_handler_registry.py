from __future__ import annotations

from collections.abc import Callable
from typing import Any

from direttore.core.contracts.handlers import (
    QueryHandler,
    QueryHandlerConfig,
)
from direttore.core.contracts.messages import Query
from direttore.core.registries.base_handler_registry import (
    BaseHandlerRegistry,
)
from direttore.core.registries.errors import (
    InvalidHandlerTypeError,
    InvalidMessageTypeError,
)
from direttore.core.registries.registrations import (
    QueryHandlerRegistration,
)


class QueryHandlerRegistry(
    BaseHandlerRegistry[QueryHandlerRegistration],
):
    def register(
        self,
        query_type: type[Query],
        handler_type: type[QueryHandler],
        *,
        key: str | None = None,
        config: QueryHandlerConfig | None = None,
    ) -> None:
        self._validate_query_type(query_type)
        self._validate_handler_type(handler_type)

        registration = QueryHandlerRegistration(
            query_type=query_type,
            handler_type=handler_type,
            key=key,
            source_name=self.source_name,
            config=config or QueryHandlerConfig(),
        )

        self._add_registration(
            message_type=query_type,
            registration=registration,
            key=key,
        )

    def decorator_register(
        self,
        query_type: type[Query],
        *,
        key: str | None = None,
        config: QueryHandlerConfig | None = None,
    ) -> Callable[[type[QueryHandler]], type[QueryHandler]]:
        def decorator(
            handler_type: type[QueryHandler],
        ) -> type[QueryHandler]:
            self.register(
                query_type=query_type,
                handler_type=handler_type,
                key=key,
                config=config,
            )

            return handler_type

        return decorator

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

    def _get_message_type(
        self,
        registration: QueryHandlerRegistration,
    ) -> type[Any]:
        return registration.query_type

    def _get_handler_type(
        self,
        registration: QueryHandlerRegistration,
    ) -> type[Any]:
        return registration.handler_type

    def _get_key(
        self,
        registration: QueryHandlerRegistration,
    ) -> str | None:
        return registration.key

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