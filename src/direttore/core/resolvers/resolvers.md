# Handler resolvers

Resolvers bridge immutable registration metadata and the app-scoped container.
They validate constructor dependencies, cache handlers without execution-local
dependencies, and return `ResolvedHandler` values.

Physical slots call resolvers exactly once per direct or keyed operation. A
keyed slot path uses the returned registration to construct the message and
then executes that same resolved handler. Operation-ID paths load the key and
payload inside the already-open lease resource scope before using the keyed
path.

Use-case and event resolvers also support lookup by stable saga key for reverse
compensation. Resolvers do not create lifecycle contexts, spans, resources, or
transactions and do not invoke handlers.
