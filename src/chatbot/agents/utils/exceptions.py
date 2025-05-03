class MaxMessageHistoryException(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class MustContainSystemMessageException(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
