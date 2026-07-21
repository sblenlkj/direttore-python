class ResolverError(Exception):
    pass


class HandlerConstructorInspectionError(ResolverError):
    pass


class HandlerDependencyResolutionError(ResolverError):
    pass


class HandlerWarmUpError(ResolverError):
    pass

class HandlerValidationError(ResolverError):
    pass