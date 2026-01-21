"""
Download client implementations.

This package provides abstract base class, registry, configuration dataclasses,
and concrete implementations for download clients.
"""
from transferarr.clients.config import ClientConfig
from transferarr.clients.download_client import DownloadClientBase
from transferarr.clients.registry import ClientRegistry, register_client
from transferarr.clients.base import load_download_clients

# Import deluge to register it (also done in base.py, but explicit here for exports)
from transferarr.clients.deluge import DelugeClient

__all__ = [
    "ClientConfig",
    "DownloadClientBase",
    "ClientRegistry",
    "register_client",
    "load_download_clients",
    "DelugeClient",
]