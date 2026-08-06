from dataclasses import dataclass
from typing import Any

from direttore import (
    InMemorySagaJournal,
    ModularMonolithDirettoreApplication,
    ModularMonolithSlotConfig,
    ModularMonolithSlotCreator,
    ModularMonolithSlotCreatorConfig,
    PoolExecutionSlotProvider,
)
from modular_monolith.bootstrap.container import build_container
from modular_monolith.bootstrap.contexts import contexts
from modular_monolith.bootstrap.coordinator import ApplicationCoordinator
from modular_monolith.bootstrap.execution_dependencies import (
    build_execution_dependencies,
)
from modular_monolith.contexts.warehouse.adapters.outbound.clients import (
    RecordingStockReceiptClient,
)
from modular_monolith.shared.database import InMemoryDatabase
from modular_monolith.shared.lifecycle import RequestInput
from modular_monolith.shared.resources import ExampleResourceHolder


@dataclass(slots=True)
class ModularWarehouseExample:
    application: ModularMonolithDirettoreApplication[RequestInput, dict[str, Any]]
    database: InMemoryDatabase
    receipt_client: RecordingStockReceiptClient
    saga_journal: InMemorySagaJournal


def build_application() -> ModularWarehouseExample:
    database = InMemoryDatabase()
    receipt_client = RecordingStockReceiptClient()
    saga_journal = InMemorySagaJournal()
    slot_creator = ModularMonolithSlotCreator(
        config=ModularMonolithSlotCreatorConfig(
            slot=ModularMonolithSlotConfig(
                resource_holder_factory=lambda: ExampleResourceHolder(
                    {"primary": database.create_session}
                ),
                coordinator_factory=lambda holder: ApplicationCoordinator(
                    resource_holder=holder
                ),
            ),
            contexts=contexts,
            saga_journal=saga_journal,
        ),
        container=build_container(receipt_client),
        execution_dependencies_registry=build_execution_dependencies(),
    )
    application = ModularMonolithDirettoreApplication(
        slot_provider=PoolExecutionSlotProvider(
            slot_creator=slot_creator,
            initial_slot_count=1,
            max_slot_count=2,
        )
    )
    application.validate()
    return ModularWarehouseExample(
        application=application,
        database=database,
        receipt_client=receipt_client,
        saga_journal=saga_journal,
    )

