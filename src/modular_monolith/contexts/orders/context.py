from direttore import ModularMonolithDirettoreContext
from modular_monolith.contexts.orders.adapters.outbound.in_memory.unit_of_work import (
    InMemoryOrdersUnitOfWork,
)
from modular_monolith.contexts.orders.application import (
    events as _events,  # noqa: F401
)
from modular_monolith.contexts.orders.application import (
    use_cases as _use_cases,  # noqa: F401
)
from modular_monolith.contexts.orders.application.architecture import (
    event_registry,
    use_case_registry,
)

orders_context = ModularMonolithDirettoreContext(
    use_case_registry=use_case_registry,
    event_registry=event_registry,
    use_case_root_uow_type=InMemoryOrdersUnitOfWork,
)

