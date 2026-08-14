from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from direttore.core.modular_monolith_support.execution_runtime import (
        ModularMonolithExecutionRuntime,
    )


@dataclass(frozen=True, slots=True)
class ModularMonolithExecutionDependencyContext:
    """Context passed to execution-scoped dependency factories.

    Execution-scoped dependencies are created for one modular-monolith execution
    runtime.

    The main use case is replacing external service clients with in-process
    clients inside a modular monolith.

    Example:

        class InProcessBillingClient:
            def __init__(
                self,
                runtime: ModularMonolithExecutionRuntime[Any, Any],
            ) -> None:
                self.runtime = runtime

            async def charge(self, command: ChargeCustomerCommand) -> Any:
                return await self.runtime.invoke(command)

        registry.register(
            dependency_type=BillingClient,
            factory=lambda context: InProcessBillingClient(context.runtime),
        )

    Handlers still depend on normal application interfaces, while the modular
    runtime provides execution-scoped in-process implementations.
    """

    runtime: ModularMonolithExecutionRuntime


type ModularMonolithExecutionDependencyFactory[DependencyT] = Callable[
    [ModularMonolithExecutionDependencyContext],
    DependencyT,
]


@dataclass(frozen=True, slots=True)
class ModularMonolithExecutionDependencyRegistration:
    dependency_type: type[Any]
    factory: ModularMonolithExecutionDependencyFactory[Any]
    implementation_type: type[Any] | None = None


class ModularMonolithExecutionDependencyRegistry:
    """Registry for modular-monolith execution-scoped dependency overrides.

    The regular Container stores app-scope dependencies.

    This registry stores factories for dependencies that must be created for a
    concrete execution runtime.

    Resolver dependency priority in modular-monolith mode should be:

        1. execution overrides built from this registry;
        2. regular Container;
        3. constructor default value;
        4. error.

    Dependencies registered here are usually lightweight wrappers around the
    current ModularMonolithExecutionRuntime.
    """

    def __init__(self) -> None:
        self._registrations: dict[
            type[Any],
            ModularMonolithExecutionDependencyRegistration,
        ] = {}

    def decorator_register[DependencyT](
        self,
        dependency_type: type[DependencyT],
        *,
        implementation_type: type[DependencyT] | None = None,
    ) -> Callable[
        [ModularMonolithExecutionDependencyFactory[DependencyT]],
        ModularMonolithExecutionDependencyFactory[DependencyT],
    ]:
        self._validate_dependency_type(dependency_type)

        def decorator(
            factory: ModularMonolithExecutionDependencyFactory[DependencyT],
        ) -> ModularMonolithExecutionDependencyFactory[DependencyT]:
            self.register(
                dependency_type=dependency_type,
                factory=factory,
                implementation_type=implementation_type,
            )

            return factory

        return decorator

    def register[DependencyT](
        self,
        *,
        dependency_type: type[DependencyT],
        factory: ModularMonolithExecutionDependencyFactory[DependencyT],
        implementation_type: type[DependencyT] | None = None,
    ) -> None:
        self._validate_dependency_type(dependency_type)
        if implementation_type is not None and not isinstance(
            implementation_type, type
        ):
            raise TypeError(
                "Execution dependency implementation type must be a type. "
                f"Got {implementation_type!r}."
            )

        if dependency_type in self._registrations:
            raise ValueError(
                "Execution dependency is already registered. "
                f"Dependency={dependency_type.__module__}."
                f"{dependency_type.__qualname__}."
            )

        self._registrations[dependency_type] = (
            ModularMonolithExecutionDependencyRegistration(
                dependency_type=dependency_type,
                factory=cast(
                    ModularMonolithExecutionDependencyFactory[Any],
                    factory,
                ),
                implementation_type=implementation_type,
            )
        )

    def build_overrides(
        self,
        *,
        context: ModularMonolithExecutionDependencyContext,
    ) -> Mapping[type[Any], Any]:
        return {
            dependency_type: registration.factory(context)
            for dependency_type, registration in self._registrations.items()
        }

    def registered_dependency_types(self) -> set[type[Any]]:
        return set(self._registrations.keys())

    def registered_dependency_implementations(
        self,
    ) -> Mapping[type[Any], type[Any] | None]:
        return {
            dependency_type: registration.implementation_type
            for dependency_type, registration in self._registrations.items()
        }

    def _validate_dependency_type(
        self,
        dependency_type: type[Any],
    ) -> None:
        if not isinstance(dependency_type, type):
            raise TypeError(f"Dependency type must be a type, got {dependency_type!r}.")
