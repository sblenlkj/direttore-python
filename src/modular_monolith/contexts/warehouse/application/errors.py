class ProductNotFoundError(LookupError):
    pass


class ProductAlreadyExistsError(ValueError):
    pass


class InsufficientStockError(ValueError):
    pass

