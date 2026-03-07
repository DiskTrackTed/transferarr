"""
Service for manual transfer operations.

Handles validation, cross-seed detection, and delegation to TorrentManager
for user-initiated transfers (bypassing the Radarr/Sonarr queue flow).
"""
import logging
from collections import defaultdict

from . import NotFoundError, ValidationError

logger = logging.getLogger("transferarr")


class ManualTransferService:
    """Service for initiating manual torrent transfers."""

    def __init__(self, torrent_manager):
        self.torrent_manager = torrent_manager

    def get_destinations(self, source_client: str) -> list:
        """Get valid destination clients for a given source client.

        A destination is valid if there is a configured connection
        from the source client to it.

        Args:
            source_client: Name of the source download client

        Returns:
            List of dicts with destination client info

        Raises:
            NotFoundError: If source client doesn't exist
        """
        if source_client not in self.torrent_manager.download_clients:
            raise NotFoundError("Client", source_client)

        destinations = []
        seen = set()
        for connection in self.torrent_manager.connections.values():
            if connection.from_client.name == source_client:
                dest_name = connection.to_client.name
                if dest_name not in seen:
                    seen.add(dest_name)
                    destinations.append({
                        "client": dest_name,
                        "connection": connection.name,
                        "transfer_type": "torrent" if connection.is_torrent_transfer else "file",
                    })
        return destinations

    def detect_cross_seeds(self, client_name: str, torrents_data: dict) -> dict:
        """Detect cross-seed groups for torrents on a client.

        Cross-seeds are torrents that share the same save_path on the same
        client (they reference the same data files).

        Args:
            client_name: Name of the download client
            torrents_data: Dict of torrent_hash -> torrent_info from the client

        Returns:
            Dict mapping save_path -> list of torrent hashes in that group
            (only groups with 2+ torrents are included)
        """
        path_groups = defaultdict(list)
        for torrent_hash, info in torrents_data.items():
            save_path = info.get("save_path")
            if save_path:
                path_groups[save_path].append(torrent_hash)

        # Only return groups with multiple torrents (actual cross-seeds)
        return {
            path: hashes
            for path, hashes in path_groups.items()
            if len(hashes) > 1
        }

    def validate_and_initiate(self, data: dict) -> dict:
        """Validate a manual transfer request and initiate the transfer.

        Args:
            data: Dict with keys:
                - hashes: list of torrent hashes to transfer
                - source_client: name of source download client
                - destination_client: name of destination download client
                - include_cross_seeds: whether to auto-include cross-seed siblings

        Returns:
            Dict with transfer summary (transfer_ids, torrents transferred)

        Raises:
            ValidationError: If request is invalid
            NotFoundError: If clients or connection not found
        """
        hashes = data.get("hashes", [])
        source_client_name = data["source_client"]
        dest_client_name = data["destination_client"]
        include_cross_seeds = data.get("include_cross_seeds", True)

        # Validate we have hashes
        if not hashes:
            raise ValidationError("No torrent hashes provided")

        # Validate clients exist
        if source_client_name not in self.torrent_manager.download_clients:
            raise NotFoundError("Client", source_client_name)
        if dest_client_name not in self.torrent_manager.download_clients:
            raise NotFoundError("Client", dest_client_name)

        # Validate source != destination
        if source_client_name == dest_client_name:
            raise ValidationError("Source and destination clients cannot be the same")

        source_client = self.torrent_manager.download_clients[source_client_name]
        dest_client = self.torrent_manager.download_clients[dest_client_name]

        # Find a connection from source to destination
        connection = None
        for conn in self.torrent_manager.connections.values():
            if (conn.from_client.name == source_client_name
                    and conn.to_client.name == dest_client_name):
                connection = conn
                break

        if not connection:
            raise ValidationError(
                f"No connection configured from '{source_client_name}' to '{dest_client_name}'"
            )

        # Validate tracker is available for torrent transfers
        if (connection.is_torrent_transfer
                and not self.torrent_manager.torrent_transfer_handler):
            raise ValidationError(
                "Tracker is not available for torrent-based transfers. "
                "Enable the tracker in Settings or use a file transfer connection."
            )

        # Validate all torrents exist on source and are seeding
        all_torrents = source_client.get_all_torrents_status() or {}
        valid_hashes = set()
        invalid_hashes = []
        not_seeding = []

        for h in hashes:
            h_lower = h.lower()
            # Check both original and lowercase
            matched_hash = None
            for existing_hash in all_torrents:
                if existing_hash.lower() == h_lower:
                    matched_hash = existing_hash
                    break

            if matched_hash is None:
                invalid_hashes.append(h)
            else:
                state = all_torrents[matched_hash].get("state", "").lower()
                if state != "seeding":
                    not_seeding.append(h)
                else:
                    valid_hashes.add(matched_hash)

        if invalid_hashes:
            raise ValidationError(
                f"Torrents not found on '{source_client_name}': {', '.join(invalid_hashes[:5])}"
            )
        if not_seeding:
            raise ValidationError(
                f"Torrents must be in 'Seeding' state to transfer. "
                f"Not seeding: {', '.join(not_seeding[:5])}"
            )

        # Check for already-tracked torrents
        tracked_hashes = {t.id.lower() for t in self.torrent_manager.torrents if t.id}
        already_tracked = [h for h in valid_hashes if h.lower() in tracked_hashes]
        if already_tracked:
            raise ValidationError(
                f"Torrents already being tracked/transferred: "
                f"{', '.join(already_tracked[:5])}"
            )

        # Expand with cross-seeds if requested
        if include_cross_seeds:
            cross_seed_groups = self.detect_cross_seeds(
                source_client_name, all_torrents
            )
            expanded = set(valid_hashes)
            for h in list(valid_hashes):
                save_path = all_torrents.get(h, {}).get("save_path")
                if save_path and save_path in cross_seed_groups:
                    for sibling in cross_seed_groups[save_path]:
                        if sibling not in expanded:
                            # Only add if sibling is also seeding and not tracked
                            sibling_state = all_torrents.get(sibling, {}).get("state", "").lower()
                            if (sibling_state == "seeding"
                                    and sibling.lower() not in tracked_hashes):
                                expanded.add(sibling)
            valid_hashes = expanded

        # Delegate to TorrentManager
        results = self.torrent_manager.create_manual_transfers(
            hashes=list(valid_hashes),
            source_client=source_client,
            dest_client=dest_client,
            connection=connection,
        )

        return results
