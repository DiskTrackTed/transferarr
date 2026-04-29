"""
Service layer for business logic extraction.

Custom exceptions allow route handlers to map errors to HTTP responses.
"""


class ServiceError(Exception):
    """Base exception for service errors"""
    pass


class NotFoundError(ServiceError):
    """Resource not found"""
    def __init__(self, resource_type: str, identifier: str):
        self.resource_type = resource_type
        self.identifier = identifier
        super().__init__(f"{resource_type} '{identifier}' not found")


class ConflictError(ServiceError):
    """Resource already exists or is in use"""
    def __init__(self, message: str):
        super().__init__(message)


class ValidationError(ServiceError):
    """Invalid input data"""
    def __init__(self, message: str, details: dict = None):
        self.details = details or {}
        super().__init__(message)


class ConfigSaveError(ServiceError):
    """Failed to save configuration"""
    pass


class ServiceUnavailableError(ServiceError):
    """A required service or client is unavailable"""

    def __init__(self, message: str, details: dict = None):
        self.details = details or {}
        super().__init__(message)


from .download_client_service import DownloadClientService
from .connection_service import ConnectionService
from .torrent_service import TorrentService
from .manual_transfer_service import ManualTransferService

__all__ = [
    'ServiceError',
    'NotFoundError', 
    'ConflictError',
    'ValidationError',
    'ConfigSaveError',
    'ServiceUnavailableError',
    'DownloadClientService',
    'ConnectionService',
    'TorrentService',
    'ManualTransferService',
]
