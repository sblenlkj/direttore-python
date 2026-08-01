# Modular UoW routing

Routing registries map resolved handler types to bounded-context root UoW
types. They express routing only.

The modular physical slot resolves a handler, asks the matching routing
registry for its UoW type, and retrieves that UoW from the slot coordinator.
The runtime uses the same lookup for nested in-process invocation. Event
dispatch uses event-handler routing.

Use-case and query UoW objects may be distinct typed facades, but every UoW in
one coordinator delegates to the same unified `ResourceHolder`. Routing
registries never create resources, invoke handlers, or finalize transactions.
