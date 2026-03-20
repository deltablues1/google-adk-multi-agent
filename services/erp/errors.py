"""ERP Business Error hierarchy with precise HTTP status codes."""


class BusinessError(Exception):
    """Base class for all ERP business rule violations."""
    http_status: int = 422

    def __init__(self, code: str, message: str, field: str = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "field": self.field}


class ValidationError(BusinessError):
    """Input validation failed — HTTP 422 Unprocessable Entity."""
    http_status = 422


class InvalidStateTransitionError(BusinessError):
    """Attempted document state transition not allowed — HTTP 409 Conflict."""
    http_status = 409


class DuplicateError(BusinessError):
    """Idempotency key already used / duplicate document — HTTP 409 Conflict."""
    http_status = 409


class NotFoundError(BusinessError):
    """Requested resource not found — HTTP 404 Not Found."""
    http_status = 404


class InsufficientPermissionError(BusinessError):
    """User lacks required permission — HTTP 403 Forbidden."""
    http_status = 403
