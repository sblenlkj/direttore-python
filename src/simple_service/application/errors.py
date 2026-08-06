class WarehouseExampleError(RuntimeError):
    pass


class ProductAlreadyExistsError(WarehouseExampleError):
    pass


class ProductNotFoundError(WarehouseExampleError):
    pass


class InsufficientStockError(WarehouseExampleError):
    pass


class OrderAlreadyExistsError(WarehouseExampleError):
    pass


class OrderNotFoundError(WarehouseExampleError):
    pass


class OrderAlreadyCancelledError(WarehouseExampleError):
    pass

