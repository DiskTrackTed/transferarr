"""
Unit tests for DownloadClientBase, ClientConfig, and ClientRegistry.
"""
import pytest
import threading
from abc import ABC
from transferarr.clients.download_client import DownloadClientBase
from transferarr.clients.config import ClientConfig
from transferarr.clients.registry import ClientRegistry, register_client
from transferarr.models.torrent import TorrentState


# Python 3.9 compatible type hints (use Optional instead of |)
from typing import Optional, Dict


def make_config(name="test", client_type="test", host="localhost", port=8080, 
                password="password", username=None, **extra):
    """Helper to create a ClientConfig for tests."""
    return ClientConfig(
        name=name,
        client_type=client_type,
        host=host,
        port=port,
        password=password,
        username=username,
        extra_config=extra
    )


def make_complete_client_class():
    """Create a complete client class for testing."""
    class CompleteClient(DownloadClientBase):
        def ensure_connected(self) -> bool:
            return True
        
        def is_connected(self) -> bool:
            return True
        
        def has_torrent(self, torrent) -> bool:
            return False
        
        def get_torrent_info(self, torrent) -> Optional[Dict]:
            return None
        
        def get_torrent_state(self, torrent) -> TorrentState:
            return TorrentState.UNCLAIMED
        
        def add_torrent_file(self, path: str, data: bytes, options: dict) -> None:
            pass
        
        def remove_torrent(self, torrent_id: str, remove_data: bool = True) -> None:
            pass
        
        def get_all_torrents_status(self) -> dict:
            return {}
        
        def test_connection(self) -> dict:
            return {"success": True, "message": "OK"}
    
    return CompleteClient


class TestClientConfig:
    """Tests for the ClientConfig dataclass."""
    
    def test_from_dict_basic(self):
        """from_dict creates config from basic dict."""
        config = ClientConfig.from_dict("my-client", {
            "type": "deluge",
            "host": "192.168.1.1",
            "port": 8112,
            "password": "secret",
        })
        
        assert config.name == "my-client"
        assert config.client_type == "deluge"
        assert config.host == "192.168.1.1"
        assert config.port == 8112
        assert config.password == "secret"
        assert config.username is None
    
    def test_from_dict_with_username(self):
        """from_dict handles optional username."""
        config = ClientConfig.from_dict("test", {
            "type": "deluge",
            "host": "localhost",
            "port": 58846,
            "password": "pass",
            "username": "admin",
        })
        
        assert config.username == "admin"
    
    def test_from_dict_extra_fields(self):
        """from_dict captures extra fields in extra_config."""
        config = ClientConfig.from_dict("test", {
            "type": "deluge",
            "host": "localhost",
            "port": 8112,
            "password": "pass",
            "connection_type": "web",
            "custom_field": "value",
        })
        
        assert config.extra_config["connection_type"] == "web"
        assert config.extra_config["custom_field"] == "value"
    
    def test_from_dict_ignores_name_in_dict(self):
        """from_dict uses name parameter, not name in dict."""
        config = ClientConfig.from_dict("correct-name", {
            "name": "wrong-name",  # Should be ignored
            "type": "deluge",
            "host": "localhost",
            "port": 8112,
            "password": "pass",
        })
        
        assert config.name == "correct-name"
        assert "name" not in config.extra_config
    
    def test_to_storage_dict(self):
        """to_storage_dict creates dict for config file."""
        config = ClientConfig(
            name="my-client",
            client_type="deluge",
            host="localhost",
            port=8112,
            password="secret",
            username="admin",
            extra_config={"connection_type": "rpc"},
        )
        
        storage = config.to_storage_dict()
        
        assert "name" not in storage  # Name is dict key, not in value
        assert storage["type"] == "deluge"
        assert storage["host"] == "localhost"
        assert storage["port"] == 8112
        assert storage["password"] == "secret"
        assert storage["username"] == "admin"
        assert storage["connection_type"] == "rpc"
    
    def test_get_extra(self):
        """get_extra retrieves client-specific config."""
        config = ClientConfig(
            name="test",
            client_type="deluge",
            host="localhost",
            port=8112,
            password="pass",
            extra_config={"connection_type": "web"},
        )
        
        assert config.get_extra("connection_type") == "web"
        assert config.get_extra("nonexistent") is None
        assert config.get_extra("nonexistent", "default") == "default"


class TestDownloadClientBase:
    """Tests for the abstract base class."""
    
    def test_cannot_instantiate_directly(self):
        """ABC prevents direct instantiation."""
        config = make_config()
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            DownloadClientBase(config)
    
    def test_incomplete_subclass_cannot_instantiate(self):
        """Subclass missing abstract methods cannot be instantiated."""
        class IncompleteClient(DownloadClientBase):
            def ensure_connected(self) -> bool:
                return True
            
            def is_connected(self) -> bool:
                return True
        
        config = make_config()
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteClient(config)
    
    def test_complete_subclass_can_instantiate(self):
        """Subclass with all abstract methods can be instantiated."""
        CompleteClient = make_complete_client_class()
        config = make_config(name="test", host="localhost", port=8080, password="password")
        
        client = CompleteClient(config)
        assert client.name == "test"
        assert client.host == "localhost"
        assert client.port == 8080
        assert client.password == "password"
    
    def test_base_class_initializes_common_properties(self):
        """Base class __init__ sets common properties from config."""
        CompleteClient = make_complete_client_class()
        config = make_config(
            name="my-client",
            host="192.168.1.1",
            port=9000,
            password="secret",
            username="admin"
        )
        
        client = CompleteClient(config)
        
        assert client.name == "my-client"
        assert client.host == "192.168.1.1"
        assert client.port == 9000
        assert client.password == "secret"
        assert client.username == "admin"
        assert client.connections == []
        assert isinstance(client._lock, type(threading.RLock()))
        assert client.config is config  # Config object is stored
    
    def test_optional_methods_raise_not_implemented(self):
        """Optional methods raise NotImplementedError by default."""
        CompleteClient = make_complete_client_class()
        config = make_config()
        client = CompleteClient(config)
        
        with pytest.raises(NotImplementedError, match="does not support start_torrent"):
            client.start_torrent("abc123")
        
        with pytest.raises(NotImplementedError, match="does not support stop_torrent"):
            client.stop_torrent("abc123")
        
        with pytest.raises(NotImplementedError, match="does not support verify_torrent"):
            client.verify_torrent("abc123")
    
    def test_add_connection_appends_to_list(self):
        """add_connection adds to connections list."""
        CompleteClient = make_complete_client_class()
        config = make_config()
        client = CompleteClient(config)
        mock_connection = object()
        
        client.add_connection(mock_connection)
        assert mock_connection in client.connections
        assert len(client.connections) == 1
    
    def test_remove_connection_removes_from_list(self):
        """remove_connection removes from connections list."""
        CompleteClient = make_complete_client_class()
        config = make_config()
        client = CompleteClient(config)
        mock_connection = object()
        
        client.add_connection(mock_connection)
        client.remove_connection(mock_connection)
        assert mock_connection not in client.connections
        assert len(client.connections) == 0


class TestClientRegistry:
    """Tests for the client registry."""
    
    def setup_method(self):
        """Clear registry before each test to avoid pollution."""
        self._original_clients = ClientRegistry._clients.copy()
    
    def teardown_method(self):
        """Restore original registry state after each test."""
        ClientRegistry._clients = self._original_clients
    
    def test_register_decorator(self):
        """@register_client decorator registers the class."""
        @register_client("test_client")
        class TestClient(DownloadClientBase):
            def ensure_connected(self) -> bool:
                return True
            def is_connected(self) -> bool:
                return True
            def has_torrent(self, torrent) -> bool:
                return False
            def get_torrent_info(self, torrent) -> Optional[Dict]:
                return None
            def get_torrent_state(self, torrent) -> TorrentState:
                return TorrentState.UNCLAIMED
            def add_torrent_file(self, path: str, data: bytes, options: dict) -> None:
                pass
            def remove_torrent(self, torrent_id: str, remove_data: bool = True) -> None:
                pass
            def get_all_torrents_status(self) -> dict:
                return {}
            def test_connection(self) -> dict:
                return {"success": True, "message": "OK"}
        
        assert "test_client" in ClientRegistry._clients
        assert ClientRegistry._clients["test_client"] is TestClient
    
    def test_create_returns_instance(self):
        """create() returns an instance of the registered class."""
        @register_client("create_test")
        class CreateTestClient(DownloadClientBase):
            def ensure_connected(self) -> bool:
                return True
            def is_connected(self) -> bool:
                return True
            def has_torrent(self, torrent) -> bool:
                return False
            def get_torrent_info(self, torrent) -> Optional[Dict]:
                return None
            def get_torrent_state(self, torrent) -> TorrentState:
                return TorrentState.UNCLAIMED
            def add_torrent_file(self, path: str, data: bytes, options: dict) -> None:
                pass
            def remove_torrent(self, torrent_id: str, remove_data: bool = True) -> None:
                pass
            def get_all_torrents_status(self) -> dict:
                return {}
            def test_connection(self) -> dict:
                return {"success": True, "message": "OK"}
        
        config = make_config(name="my-name", client_type="create_test", host="localhost")
        client = ClientRegistry.create(config)
        
        assert isinstance(client, CreateTestClient)
        assert client.name == "my-name"
        assert client.host == "localhost"
    
    def test_create_from_dict(self):
        """create_from_dict() creates client from config dict."""
        @register_client("dict_test")
        class DictTestClient(DownloadClientBase):
            def ensure_connected(self) -> bool:
                return True
            def is_connected(self) -> bool:
                return True
            def has_torrent(self, torrent) -> bool:
                return False
            def get_torrent_info(self, torrent) -> Optional[Dict]:
                return None
            def get_torrent_state(self, torrent) -> TorrentState:
                return TorrentState.UNCLAIMED
            def add_torrent_file(self, path: str, data: bytes, options: dict) -> None:
                pass
            def remove_torrent(self, torrent_id: str, remove_data: bool = True) -> None:
                pass
            def get_all_torrents_status(self) -> dict:
                return {}
            def test_connection(self) -> dict:
                return {"success": True, "message": "OK"}
        
        client = ClientRegistry.create_from_dict("my-name", {
            "type": "dict_test",
            "host": "192.168.1.1",
            "port": 8080,
            "password": "pass",
        })
        
        assert isinstance(client, DictTestClient)
        assert client.name == "my-name"
        assert client.host == "192.168.1.1"
    
    def test_create_unknown_type_raises_valueerror(self):
        """create() raises ValueError for unknown client types."""
        config = make_config(client_type="nonexistent")
        with pytest.raises(ValueError, match="Unknown client type: 'nonexistent'"):
            ClientRegistry.create(config)
    
    def test_get_supported_types(self):
        """get_supported_types() returns list of registered types."""
        supported = ClientRegistry.get_supported_types()
        assert "deluge" in supported
        assert isinstance(supported, list)
    
    def test_is_supported(self):
        """is_supported() returns True for registered types."""
        assert ClientRegistry.is_supported("deluge") is True
        assert ClientRegistry.is_supported("nonexistent") is False


class TestDelugeClientRegistration:
    """Tests that DelugeClient is properly registered."""
    
    def test_deluge_is_registered(self):
        """DelugeClient is registered as 'deluge'."""
        assert "deluge" in ClientRegistry.get_supported_types()
        assert ClientRegistry.is_supported("deluge")
    
    def test_deluge_inherits_from_base(self):
        """DelugeClient inherits from DownloadClientBase."""
        from transferarr.clients.deluge import DelugeClient
        assert issubclass(DelugeClient, DownloadClientBase)
