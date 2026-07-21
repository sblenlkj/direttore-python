class EngineError(Exception):
    pass


class EngineEventLimitExceededError(EngineError):
    pass


class UnsupportedUseCaseExecutionModeError(EngineError):
    pass