from direttore import ModularMonolithDirettoreContext
from modular_monolith.contexts.warehouse.adapters.outbound.in_memory.unit_of_work import (
    InMemoryWarehouseUnitOfWork,
)
from modular_monolith.contexts.warehouse.application import (
    events as _events,  # noqa: F401
)
from modular_monolith.contexts.warehouse.application import (
    use_cases as _use_cases,  # noqa: F401
)
from modular_monolith.contexts.warehouse.application.architecture import (
    event_registry,
    use_case_registry,
)

warehouse_context = ModularMonolithDirettoreContext(
    use_case_registry=use_case_registry,
    event_registry=event_registry,
    use_case_root_uow_type=InMemoryWarehouseUnitOfWork,
)

