from dataclasses import dataclass
from typing import Any

from direttore import (
    InMemorySagaJournal,
    PoolExecutionSlotProvider,
    SimpleServiceDirettoreApplication,
    SimpleServiceHandlerConfig,
    SimpleServiceSlotConfig,
    SimpleServiceSlotCreator,
    SimpleServiceSlotCreatorConfig,
    SimpleServiceUseCaseExecutionConfig,
)
from simple_service.adapters.outbound.clients import RecordingStockReceiptClient
from simple_service.adapters.outbound.in_memory.database import InMemoryDatabase
from simple_service.adapters.outbound.in_memory.unit_of_work import (
    InMemoryApplicationUnitOfWork,
)
from simple_service.bootstrap.container import build_container
from simple_service.bootstrap.registries import event_registry, use_case_registry
from simple_service.shared.lifecycle import RequestInput
from simple_service.shared.resources import (
    ExampleResourceHolder,
    InMemoryOperationLoader,
)


@dataclass(slots=True)
class SimpleWarehouseExample:
    application: SimpleServiceDirettoreApplication[RequestInput, dict[str, Any]]
    database: InMemoryDatabase
    receipt_client: RecordingStockReceiptClient
    saga_journal: InMemorySagaJournal


def build_application() -> SimpleWarehouseExample:
    database = InMemoryDatabase()
    receipt_client = RecordingStockReceiptClient()
    saga_journal = InMemorySagaJournal()
    slot_creator = SimpleServiceSlotCreator(
        config=SimpleServiceSlotCreatorConfig(
            slot=SimpleServiceSlotConfig(
                resource_holder_factory=lambda: ExampleResourceHolder(
                    {"primary": database.create_session}
                ),
                uow_factory=InMemoryApplicationUnitOfWork,
            ),
            handlers=SimpleServiceHandlerConfig(
                use_case_registry=use_case_registry,
                event_registry=event_registry,
            ),
            saga_journal=saga_journal,
            use_case_execution=SimpleServiceUseCaseExecutionConfig(
                operation_loader=InMemoryOperationLoader(),
            ),
        ),
        container=build_container(receipt_client),
    )
    application = SimpleServiceDirettoreApplication(
        slot_provider=PoolExecutionSlotProvider(
            slot_creator=slot_creator,
            initial_slot_count=1,
            max_slot_count=2,
        )
    )
    application.validate()
    return SimpleWarehouseExample(
        application=application,
        database=database,
        receipt_client=receipt_client,
        saga_journal=saga_journal,
    )

