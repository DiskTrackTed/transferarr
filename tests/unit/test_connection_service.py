"""Unit tests for ConnectionService chain warnings."""

from unittest.mock import Mock

import pytest

from transferarr.web.services.connection_service import ConnectionService


def _expected_warning(
    connection_path: str,
    chain_path: str,
    source_client: str,
    intermediate_client: str,
    destination_client: str,
) -> str:
    return (
        f"Connection {connection_path} creates a chain ({chain_path}). "
        "Transferarr does not support multi-hop transfers. "
        f"Torrents on {source_client} will transfer to {intermediate_client} "
        f"but will NOT automatically continue to {destination_client}."
    )


def _make_client(name: str) -> Mock:
    client = Mock()
    client.name = name
    return client


def _make_runtime_connection(name: str, from_client: Mock, to_client: Mock) -> Mock:
    connection = Mock()
    connection.name = name
    connection.from_client = from_client
    connection.to_client = to_client
    return connection


def _make_manager(existing_connections=None) -> Mock:
    existing_connections = existing_connections or []
    client_names = {"client-a", "client-b", "client-c", "client-d"}
    for _, from_client, to_client in existing_connections:
        client_names.add(from_client)
        client_names.add(to_client)

    download_clients = {
        name: _make_client(name)
        for name in sorted(client_names)
    }

    runtime_connections = {}
    config_connections = {}
    for connection_name, from_client, to_client in existing_connections:
        runtime_connections[connection_name] = _make_runtime_connection(
            connection_name,
            download_clients[from_client],
            download_clients[to_client],
        )
        config_connections[connection_name] = {
            "from": from_client,
            "to": to_client,
            "transfer_config": {"type": "torrent"},
        }

    manager = Mock()
    manager.download_clients = download_clients
    manager.connections = runtime_connections
    manager.config = {"connections": config_connections}
    manager.save_config.return_value = True
    return manager


@pytest.fixture(autouse=True)
def patch_transfer_connection(monkeypatch):
    def _make_connection(name, connection_config, from_client_obj, to_client_obj):
        connection = Mock()
        connection.name = name
        connection.from_client = from_client_obj
        connection.to_client = to_client_obj
        connection.transfer_config = connection_config["transfer_config"]
        return connection

    monkeypatch.setattr(
        "transferarr.web.services.connection_service.TransferConnection",
        _make_connection,
    )


class TestConnectionServiceWarnings:
    def test_add_connection_returns_no_warnings_for_isolated_connection(self):
        service = ConnectionService(_make_manager())

        result = service.add_connection({
            "name": "isolated",
            "from": "client-a",
            "to": "client-b",
            "transfer_config": {"type": "torrent"},
        })

        assert result["warnings"] == []
        assert result["connection"] == {
            "name": "isolated",
            "from": "client-a",
            "to": "client-b",
        }

    def test_add_connection_warns_for_inbound_chain(self):
        service = ConnectionService(_make_manager([
            ("a-to-b", "client-a", "client-b"),
        ]))

        result = service.add_connection({
            "name": "b-to-c",
            "from": "client-b",
            "to": "client-c",
            "transfer_config": {"type": "torrent"},
        })

        assert result["warnings"] == [
            _expected_warning(
                "client-b -> client-c",
                "client-a -> client-b -> client-c",
                "client-a",
                "client-b",
                "client-c",
            )
        ]

    def test_add_connection_warns_for_outbound_chain(self):
        service = ConnectionService(_make_manager([
            ("b-to-c", "client-b", "client-c"),
        ]))

        result = service.add_connection({
            "name": "a-to-b",
            "from": "client-a",
            "to": "client-b",
            "transfer_config": {"type": "torrent"},
        })

        assert result["warnings"] == [
            _expected_warning(
                "client-a -> client-b",
                "client-a -> client-b -> client-c",
                "client-a",
                "client-b",
                "client-c",
            )
        ]

    def test_add_connection_warns_for_multiple_immediate_neighbors(self):
        service = ConnectionService(_make_manager([
            ("a-to-b", "client-a", "client-b"),
            ("d-to-b", "client-d", "client-b"),
            ("c-to-d", "client-c", "client-d"),
        ]))

        result = service.add_connection({
            "name": "b-to-c",
            "from": "client-b",
            "to": "client-c",
            "transfer_config": {"type": "torrent"},
        })

        assert set(result["warnings"]) == {
            _expected_warning(
                "client-b -> client-c",
                "client-a -> client-b -> client-c",
                "client-a",
                "client-b",
                "client-c",
            ),
            _expected_warning(
                "client-b -> client-c",
                "client-d -> client-b -> client-c",
                "client-d",
                "client-b",
                "client-c",
            ),
            _expected_warning(
                "client-b -> client-c",
                "client-b -> client-c -> client-d",
                "client-b",
                "client-c",
                "client-d",
            ),
        }

    def test_add_connection_deduplicates_duplicate_paths(self):
        service = ConnectionService(_make_manager([
            ("a-to-b-1", "client-a", "client-b"),
            ("a-to-b-2", "client-a", "client-b"),
        ]))

        result = service.add_connection({
            "name": "b-to-c",
            "from": "client-b",
            "to": "client-c",
            "transfer_config": {"type": "torrent"},
        })

        assert result["warnings"] == [
            _expected_warning(
                "client-b -> client-c",
                "client-a -> client-b -> client-c",
                "client-a",
                "client-b",
                "client-c",
            )
        ]

    def test_add_connection_only_warns_for_immediate_chain(self):
        service = ConnectionService(_make_manager([
            ("a-to-b", "client-a", "client-b"),
            ("b-to-c", "client-b", "client-c"),
        ]))

        result = service.add_connection({
            "name": "c-to-d",
            "from": "client-c",
            "to": "client-d",
            "transfer_config": {"type": "torrent"},
        })

        assert result["warnings"] == [
            _expected_warning(
                "client-c -> client-d",
                "client-b -> client-c -> client-d",
                "client-b",
                "client-c",
                "client-d",
            )
        ]

    def test_add_connection_warns_once_for_reverse_edge_cycle(self):
        service = ConnectionService(_make_manager([
            ("a-to-b", "client-a", "client-b"),
        ]))

        result = service.add_connection({
            "name": "b-to-a",
            "from": "client-b",
            "to": "client-a",
            "transfer_config": {"type": "torrent"},
        })

        assert result["warnings"] == [
            _expected_warning(
                "client-b -> client-a",
                "client-a -> client-b -> client-a",
                "client-a",
                "client-b",
                "client-a",
            )
        ]

    def test_update_connection_replaces_old_edge_before_warning_check(self):
        service = ConnectionService(_make_manager([
            ("a-to-b", "client-a", "client-b"),
            ("b-to-c", "client-b", "client-c"),
        ]))

        result = service.update_connection("b-to-c", {
            "from": "client-b",
            "to": "client-d",
            "transfer_config": {"type": "torrent"},
        })

        assert result["warnings"] == [
            _expected_warning(
                "client-b -> client-d",
                "client-a -> client-b -> client-d",
                "client-a",
                "client-b",
                "client-d",
            )
        ]
        assert all("client-c" not in warning for warning in result["warnings"])

    def test_add_connection_warns_when_client_name_contains_path_delimiter(self):
        service = ConnectionService(_make_manager([
            ("upstream", "client-a", "Media -> EU"),
        ]))

        result = service.add_connection({
            "name": "downstream",
            "from": "Media -> EU",
            "to": "client-c",
            "transfer_config": {"type": "torrent"},
        })

        assert result["warnings"] == [
            _expected_warning(
                "Media -> EU -> client-c",
                "client-a -> Media -> EU -> client-c",
                "client-a",
                "Media -> EU",
                "client-c",
            )
        ]