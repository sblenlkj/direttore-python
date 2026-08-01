class RegistryError(Exception):
    pass


class HandlerAlreadyRegisteredError(RegistryError):
    pass


class HandlerKeyAlreadyRegisteredError(RegistryError):
    pass


class HandlerNotRegisteredError(RegistryError):
    pass


class HandlerKeyNotRegisteredError(RegistryError):
    pass


class InvalidHandlerTypeError(RegistryError):
    pass


class InvalidMessageTypeError(RegistryError):
    pass
