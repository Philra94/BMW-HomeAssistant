class BMWCarDataError(Exception):
    """Base BMW CarData integration error."""


class BMWAuthError(BMWCarDataError):
    """Authentication flow error."""


class BMWAuthPendingError(BMWAuthError):
    """The BMW device flow is still waiting for user approval."""


class BMWRateLimitError(BMWCarDataError):
    """BMW rejected the request because of rate limiting."""


class BMWReauthRequiredError(BMWAuthError):
    """Stored credentials are no longer sufficient and reauth is required."""
