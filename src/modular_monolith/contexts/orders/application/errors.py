class OrderNotFoundError(LookupError):
    pass


class OrderAlreadyExistsError(ValueError):
    pass


class OrderAlreadyCancelledError(ValueError):
    pass

