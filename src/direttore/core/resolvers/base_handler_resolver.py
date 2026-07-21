from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from typing import Any, cast, get_type_hints

from direttore.core.primitives.container import Container
from direttore.core.resolvers.errors import (
    HandlerConstructorInspectionError,
    HandlerDependencyResolutionError,
    HandlerValidationError,
    HandlerWarmUpError,
)
from direttore.core.resolvers.resolved_handlers import (
    ResolvedHandler,
)


class BaseHandlerResolver[RegistrationT, HandlerT](ABC):
    """Base warm-up cache auto-wiring handler resolver.

    The resolver owns handler construction logic.

    It inspects handler constructor parameters, resolves dependencies from
    explicit runtime overrides first and from the container second, then creates
    handler instances.

    Handlers that do not depend on execution-scoped dependency types are cached.
    Handlers that depend on execution-scoped objects are created per resolve.
    """

    def __init__(
        self,
        container: Container,
        *,
        execution_dependency_types: Iterable[type[Any]] = (),
    ) -> None:
        self.container = container
        self.execution_dependency_types = frozenset(execution_dependency_types)
        self._handler_cache: dict[type[Any], Any] = {}

    def warm_up_cache(
        self,
        registrations: Iterable[RegistrationT],
    ) -> None:
        for registration in registrations:
            handler_type = self._get_handler_type(registration)

            if self._uses_execution_dependencies(handler_type):
                continue

            try:
                self._handler_cache[handler_type] = self._create_handler(
                    handler_type=handler_type,
                    overrides={},
                )
            except Exception as exc:
                raise HandlerWarmUpError(
                    f"Failed to warm up handler "
                    f"'{handler_type.__module__}.{handler_type.__qualname__}'."
                ) from exc

    def validate_handlers(
        self,
        registrations: Iterable[RegistrationT],
    ) -> None:
        validation_errors: list[str] = []

        for registration in registrations:
            handler_type = self._get_handler_type(registration)

            try:
                self._validate_handler_dependencies(handler_type)
            except (
                HandlerConstructorInspectionError,
                HandlerDependencyResolutionError,
            ) as exc:
                validation_errors.append(str(exc))

        if not validation_errors:
            return

        joined_errors = "\n".join(
            f"- {error}" for error in validation_errors
        )

        raise HandlerValidationError(
            f"Handler validation failed:\n{joined_errors}"
        )

    def resolve(
        self,
        registration: RegistrationT,
        *,
        overrides: Mapping[type[Any], Any] | None = None,
    ) -> ResolvedHandler[HandlerT, RegistrationT]:
        handler_type = self._get_handler_type(registration)
        handler = self.resolve_handler(
            handler_type=handler_type,
            overrides=overrides,
        )

        return ResolvedHandler(
            handler=handler,
            handler_type=handler_type,
            registration=registration,
        )

    def resolve_handler(
        self,
        handler_type: type[HandlerT],
        *,
        overrides: Mapping[type[Any], Any] | None = None,
    ) -> HandlerT:
        if handler_type in self._handler_cache:
            return cast(HandlerT, self._handler_cache[handler_type])

        resolved_overrides = overrides or {}

        handler = self._create_handler(
            handler_type=handler_type,
            overrides=resolved_overrides,
        )

        if not self._uses_execution_dependencies(handler_type):
            self._handler_cache[handler_type] = handler

        return handler

    def _validate_handler_dependencies(
        self,
        handler_type: type[HandlerT],
    ) -> None:
        for parameter in self._iter_constructor_parameters(handler_type):
            dependency_type = self._get_parameter_dependency_type(
                handler_type=handler_type,
                parameter=parameter,
            )

            if self._is_execution_dependency_type(dependency_type):
                continue

            if self.container.has(dependency_type):
                continue

            if parameter.default is not inspect.Parameter.empty:
                continue

            raise HandlerDependencyResolutionError(
                f"Cannot resolve dependency '{parameter.name}' "
                f"of type '{dependency_type}' for handler "
                f"'{handler_type.__module__}.{handler_type.__qualname__}'."
            )

    def _create_handler(
        self,
        *,
        handler_type: type[HandlerT],
        overrides: Mapping[type[Any], Any],
    ) -> HandlerT:
        kwargs: dict[str, Any] = {}

        for parameter in self._iter_constructor_parameters(handler_type):
            dependency_type = self._get_parameter_dependency_type(
                handler_type=handler_type,
                parameter=parameter,
            )

            if dependency_type in overrides:
                kwargs[parameter.name] = overrides[dependency_type]
                continue

            if self.container.has(dependency_type):
                kwargs[parameter.name] = self.container.get(dependency_type)
                continue

            if parameter.default is not inspect.Parameter.empty:
                continue

            raise HandlerDependencyResolutionError(
                f"Cannot resolve dependency '{parameter.name}' "
                f"of type '{dependency_type}' for handler "
                f"'{handler_type.__module__}.{handler_type.__qualname__}'."
            )

        return handler_type(**kwargs)

    def _iter_constructor_parameters(
        self,
        handler_type: type[Any],
    ) -> list[inspect.Parameter]:
        try:
            signature = inspect.signature(handler_type)
        except (TypeError, ValueError) as exc:
            raise HandlerConstructorInspectionError(
                f"Cannot inspect constructor for handler "
                f"'{handler_type.__module__}.{handler_type.__qualname__}'."
            ) from exc

        parameters: list[inspect.Parameter] = []

        for parameter in signature.parameters.values():
            if parameter.kind in {
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }:
                continue

            parameters.append(parameter)

        return parameters

    def _get_parameter_dependency_type(
        self,
        *,
        handler_type: type[Any],
        parameter: inspect.Parameter,
    ) -> type[Any]:
        try:
            type_hints = get_type_hints(handler_type.__init__)
        except Exception as exc:
            raise HandlerConstructorInspectionError(
                f"Cannot read type hints for handler "
                f"'{handler_type.__module__}.{handler_type.__qualname__}'."
            ) from exc

        dependency_type = type_hints.get(
            parameter.name,
            parameter.annotation,
        )

        if dependency_type is inspect.Parameter.empty:
            if parameter.default is not inspect.Parameter.empty:
                raise HandlerDependencyResolutionError(
                    f"Optional constructor parameter '{parameter.name}' "
                    f"of handler "
                    f"'{handler_type.__module__}.{handler_type.__qualname__}' "
                    f"has no type annotation. Add a type annotation or remove "
                    f"the parameter from the constructor."
                )

            raise HandlerDependencyResolutionError(
                f"Required constructor parameter '{parameter.name}' "
                f"of handler "
                f"'{handler_type.__module__}.{handler_type.__qualname__}' "
                f"has no type annotation."
            )

        if not isinstance(dependency_type, type):
            raise HandlerDependencyResolutionError(
                f"Constructor parameter '{parameter.name}' of handler "
                f"'{handler_type.__module__}.{handler_type.__qualname__}' "
                f"must be annotated with a concrete class type. Got "
                f"'{dependency_type}'."
            )

        return dependency_type

    def _uses_execution_dependencies(
        self,
        handler_type: type[Any],
    ) -> bool:
        for parameter in self._iter_constructor_parameters(handler_type):
            dependency_type = self._get_parameter_dependency_type(
                handler_type=handler_type,
                parameter=parameter,
            )

            if self._is_execution_dependency_type(dependency_type):
                return True

        return False

    def _is_execution_dependency_type(
        self,
        dependency_type: type[Any],
    ) -> bool:
        return dependency_type in self.execution_dependency_types

    @abstractmethod
    def _get_handler_type(
        self,
        registration: RegistrationT,
    ) -> type[HandlerT]:
        raise NotImplementedError