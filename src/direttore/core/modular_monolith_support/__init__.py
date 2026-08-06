from typing import TYPE_CHECKING, Any

from .coordinator import ModularUnitOfWorkCoordinator
from .execution_dependencies import (
    ModularMonolithExecutionDependencyContext,
    ModularMonolithExecutionDependencyRegistry,
)

if TYPE_CHECKING:
    from .execution_runtime import ModularMonolithExecutionRuntime

__all__ = [
    "ModularMonolithExecutionDependencyContext",
    "ModularMonolithExecutionDependencyRegistry",
    "ModularMonolithExecutionRuntime",
    "ModularUnitOfWorkCoordinator",
]


def __getattr__(name: str) -> Any:
    if name == "ModularMonolithExecutionRuntime":
        from .execution_runtime import ModularMonolithExecutionRuntime

        return ModularMonolithExecutionRuntime
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
