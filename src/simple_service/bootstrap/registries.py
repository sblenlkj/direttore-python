from simple_service.application import events as _events  # noqa: F401
from simple_service.application import inventory as _inventory  # noqa: F401
from simple_service.application import orders as _orders  # noqa: F401
from simple_service.application.architecture import (
    event_registry,
    use_case_registry,
)

__all__ = ["event_registry", "use_case_registry"]
