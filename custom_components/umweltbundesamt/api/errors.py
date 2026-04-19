"""Exceptions raised by the Umweltbundesamt API client."""
from __future__ import annotations


class UBAError(Exception):
    """Base exception for UBA client errors."""


class UBAApiError(UBAError):
    """Raised when the API returns an error status or unexpected shape."""


class UBATimeoutError(UBAError):
    """Raised when the API does not respond in time."""
