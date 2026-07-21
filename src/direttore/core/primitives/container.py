from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast


class ContainerError(Exception):
    pass


class DependencyNotRegisteredError(ContainerError):
    pass


@dataclass(slots=True)
class Container:
    """Simple dependency container.

    Container stores long-lived dependencies by their type.

    It is used by resolvers and application/bootstrap code to instantiate
    handlers and other reusable objects. It is not request-scoped. Request or
    execution-scoped resources should live in ResourceHolder instead.
    """

    _dependencies: dict[type[Any], Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        dependencies: Mapping[type[Any], Any],
    ) -> Container:
        return cls(_dependencies=dict(dependencies))

    def set(
        self,
        dependency_type: type[Any],
        dependency: Any,
    ) -> None:
        self._dependencies[dependency_type] = dependency

    def get[T](
        self,
        dependency_type: type[T],
    ) -> T:
        dependency = self._dependencies.get(dependency_type)

        if dependency is None:
            raise DependencyNotRegisteredError(
                "No dependency registered in container. "
                f"Dependency={dependency_type.__module__}."
                f"{dependency_type.__qualname__}."
            )

        return cast(T, dependency)

    def has(
        self,
        dependency_type: type[Any],
    ) -> bool:
        return dependency_type in self._dependencies

    def merge(
        self,
        other: Container,
    ) -> Container:
        return Container.from_mapping(
            {
                **self._dependencies,
                **other._dependencies,
            }
        )

    @classmethod
    def merge_many(
        cls,
        containers: list[Container],
    ) -> Container:
        merged = cls()

        for container in containers:
            for dependency_type, dependency in container._dependencies.items():
                merged.set(
                    dependency_type=dependency_type,
                    dependency=dependency,
                )

        return merged