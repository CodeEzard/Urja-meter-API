class PortalException(Exception):
    """Base exception for upstream portal interactions."""
    pass


class PortalAuthError(PortalException):
    """Raised when authentication with the portal fails."""
    pass


class PortalRequestError(PortalException):
    """Raised when an upstream request returns a non-2xx status."""
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class ResourceNotFoundError(PortalException):
    """Raised when a requested resource (e.g., meter, transformer) is not found."""
    pass
