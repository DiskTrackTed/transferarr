from __future__ import annotations

import logging
import time
import requests
from transferarr.utils import decode_bytes
from deluge_client import DelugeRPCClient
from transferarr.models.torrent import TorrentState
from transferarr.clients.download_client import DownloadClientBase
from transferarr.clients.config import ClientConfig
from transferarr.clients.registry import register_client

logger = logging.getLogger(__name__)


@register_client("deluge")
class DelugeClient(DownloadClientBase):
    """Deluge download client implementation.
    
    Supports both RPC (daemon) and Web UI connection types.
    
    Attributes:
        connection_type: Connection method ("rpc" or "web")
        rpc_client: DelugeRPCClient instance (RPC mode only)
        base_url: Web UI base URL (Web mode only)
        web_authenticated: Whether web authentication succeeded (Web mode only)
        session: requests.Session for web API calls (Web mode only)
    """
    
    def __init__(self, config: ClientConfig):
        """Initialize Deluge client.
        
        Args:
            config: ClientConfig instance with all configuration
        """
        super().__init__(config)
        self.type = "deluge"
        
        # Get connection_type from config (defaults to RPC)
        self.connection_type = config.get_extra("connection_type", "rpc")
        
        self.rpc_client = None
        if self.connection_type == "web":
            self.base_url = f"http://{self.host}:{self.port}"
            self.web_authenticated = False
            self.session = requests.Session()

        self._connect()
    
    def _connect(self, handle_exception=True):
        """Connect to the Deluge rpc_client with proper error handling"""
        if self.connection_type == "web":
            logger.debug(f"Connecting to Deluge Web client at {self.base_url}")
            url = f"{self.base_url}/json"
            payload = {
                "method": "auth.login",
                "params": [self.password],
                "id": 1
            }
            response = self.session.post(url, json=payload)
            if response.status_code == 200 and response.json().get("result") is True:
                self.web_authenticated = True
            else:
                self.web_authenticated = False
                if handle_exception:
                    logger.error(f"Failed to authenticate with Deluge Web client: {response.status_code} - {response.text}")
                else:
                    raise Exception(f"Web client authentication failed: {response.status_code} - {response.text}")
        elif self.connection_type == "rpc":
            try:
                self.rpc_client = DelugeRPCClient(
                    host=self.host, 
                    port=self.port, 
                    username=self.username, 
                    password=self.password,
                    automatic_reconnect=True,
                    decode_utf8=True,
                )
                self.rpc_client.connect()
                if self.rpc_client.connected:
                    logger.info(f"Connected to {self.name} deluge on {self.host}:{self.port}")
                else:
                    logger.error(f"Failed to connect to {self.name} deluge on {self.host}:{self.port}")
            except Exception as e:
                if handle_exception:
                    logger.error(f"Error connecting to {self.name} deluge: {e}")
                else:
                    raise e
        else:
            logger.error(f"Unsupported connection type: {self.connection_type}")
            if not handle_exception:
                raise ValueError(f"Unsupported connection type: {self.connection_type}")

    def ensure_connected(self):
        """Ensure rpc_client is connected, reconnect if needed"""
        with self._lock:
            if self.connection_type == "web":
                self._connect()
                return self.web_authenticated
            elif self.connection_type == "rpc":
                if not self.rpc_client or not self.is_connected():
                    logger.debug(f"Reconnecting to {self.name} deluge...")
                    self._connect()
                return self.is_connected()
            else:
                logger.error(f"Unsupported connection type: {self.connection_type}")
                return False

    def _send_web_request(self, method, params, id=1):
        """Send a request to the Deluge Web client"""
        url = f"{self.base_url}/json"
        payload = {
            "method": method,
            "params": params,
            "id": id
        }
        response = self.session.post(url, json=payload)
        if response.status_code != 200:
            logger.error(f"Failed to send request to Deluge Web client: HTTP {response.status_code} - {response.text}")
            raise Exception(f"Web client error: HTTP {response.status_code}")
        return response.json()

    def _apply_label(self, torrent_hash: str, label: str = "transferarr"):
        """Apply a label to a torrent if the Label plugin is available.
        
        This is a best-effort operation - if the Label plugin isn't enabled,
        we silently skip labeling. This makes transfer torrents easily
        identifiable and filterable in Deluge's UI.
        
        Args:
            torrent_hash: The hash of the torrent to label
            label: The label to apply (default: "transferarr")
        """
        try:
            # Check if Label plugin is enabled
            if self.connection_type == "web":
                result = self._send_web_request("core.get_enabled_plugins", [], id=10)
                plugins = result.get("result", [])
            else:
                plugins = self.rpc_client.core.get_enabled_plugins()
                plugins = decode_bytes(plugins) if plugins else []
            
            if "Label" not in plugins:
                logger.debug(f"Label plugin not enabled on {self.name}, skipping label")
                return
            
            # Ensure the label exists
            if self.connection_type == "web":
                result = self._send_web_request("label.get_labels", [], id=11)
                labels = result.get("result", [])
            else:
                labels = self.rpc_client.call("label.get_labels")
                labels = decode_bytes(labels) if labels else []
            
            if label not in labels:
                logger.debug(f"Creating label '{label}' on {self.name}")
                if self.connection_type == "web":
                    self._send_web_request("label.add", [label], id=12)
                else:
                    self.rpc_client.call("label.add", label)
            
            # Apply the label to the torrent
            if self.connection_type == "web":
                self._send_web_request("label.set_torrent", [torrent_hash, label], id=13)
            else:
                self.rpc_client.call("label.set_torrent", torrent_hash, label)
            
            logger.debug(f"Applied label '{label}' to torrent {torrent_hash[:8]}... on {self.name}")
            
        except Exception as e:
            # Don't fail the operation if labeling fails
            logger.warning(f"Failed to apply label to torrent on {self.name}: {e}")

    def add_torrent_file(self, torrent_file_path, torrent_file_data, options) -> str:
        """Add a torrent from a .torrent file.
        
        Args:
            torrent_file_path: Filename for the torrent (used for display)
            torrent_file_data: Base64 encoded .torrent file contents
            options: Dict of torrent options (download_location, add_paused, etc.)
            
        Returns:
            The torrent hash of the added torrent
            
        Raises:
            ConnectionError: If not connected to Deluge
            Exception: If adding fails
        """
        with self._lock:
            if not self.ensure_connected():
                raise ConnectionError(f"Not connected to {self.name} deluge")
            try:
                if self.connection_type == "web":
                    result = self._send_web_request(
                        "core.add_torrent_file",
                        [torrent_file_path, decode_bytes(torrent_file_data), options],
                        id=3
                    )
                    torrent_hash = result.get("result")
                    if not torrent_hash:
                        error = result.get("error", {})
                        error_msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
                        raise Exception(f"Failed to add torrent file: {error_msg}")
                    return torrent_hash
                else:
                    torrent_hash = self.rpc_client.core.add_torrent_file(torrent_file_path, torrent_file_data, options)
                    if not torrent_hash:
                        raise Exception("Failed to add torrent file: no hash returned")
                    return decode_bytes(torrent_hash) if isinstance(torrent_hash, bytes) else torrent_hash
            except Exception as e:
                logger.error(f"Error adding torrent file: {e}")
                raise e

    def is_connected(self):
        try:
            if self.connection_type == "web":
                return self.web_authenticated
            else:
                return self.rpc_client.connected
        except:
            return False
    
    def has_torrent(self, torrent):
        with self._lock:
            if not self.ensure_connected():
                return False
            try:
                if self.connection_type == "web":
                    result = self._send_web_request(
                        "web.update_ui",
                        [["name", "state"], {}],
                        id=3
                    )
                    # Handle None response (e.g., during Deluge restart)
                    if not result.get('result') or not result['result'].get('torrents'):
                        logger.debug(f"No torrents data from {self.name} web client")
                        return False
                    current_torrents = result['result']['torrents']
                else:
                    current_torrents = decode_bytes(self.rpc_client.core.get_torrents_status({}, ['name']))
                    if current_torrents is None:
                        return False
                for key in current_torrents:
                    if key == torrent.id:
                        return True
                return False
            except Exception as e:
                logger.error(f"Error checking if {self.name} has torrent {torrent.name}: {e}")
                return False
    
    def get_torrent_info(self, torrent):
        old_info = None
        if torrent.home_client and torrent.home_client.name == self.name:
            old_info = torrent.home_client_info
        elif torrent.target_client and torrent.target_client.name == self.name:
            old_info = torrent.target_client_info
        with self._lock:
            if not self.ensure_connected():
                logger.debug(f"Not connected to {self.name} deluge")
                return old_info
            
            try:
                if self.connection_type == "web":
                    result = self._send_web_request(
                        "web.update_ui",
                        [["name", "state", "files", "progress", "total_size", "save_path"], {}],
                        id=3
                    )
                    # Handle None response (e.g., during Deluge restart)
                    if not result.get('result') or not result['result'].get('torrents'):
                        logger.debug(f"No torrents data from {self.name} web client")
                        return old_info
                    current_torrents = result['result']['torrents']
                else:
                    current_torrents = decode_bytes(
                        self.rpc_client.core.get_torrents_status({}, [
                            'name', 'state', 'files', 'progress', 'total_size', 'save_path'
                            ]))
                    if current_torrents is None:
                        return old_info
                for key in current_torrents:
                    if key.lower() == torrent.id:
                        return current_torrents[key]
                logger.debug(f"Torrent {torrent.name} not found in {self.name} deluge")
                return old_info
            except Exception as e:
                logger.error(f"Error getting torrent info for {torrent.name} from {self.name}: {e}")
                return old_info
    
    def get_torrent_state(self, torrent):
        try:
            if torrent.home_client and torrent.home_client.name == self.name:
                info = self.get_torrent_info(torrent)
                if not info:
                    logger.debug(f"Torrent {torrent.name} info not found in home rpc_client {self.name}")
                    return TorrentState.ERROR
                
                torrent.set_home_client_info(info)
                torrent.set_progress_from_home_client_info()
                try:
                    state_name = f"HOME_{info['state'].upper()}"
                    return TorrentState[state_name]
                except (KeyError, AttributeError) as e:
                    logger.error(f"Invalid state for torrent {torrent.name}: {info.get('state', 'None')}")
                    return TorrentState.ERROR
                    
            elif torrent.target_client and torrent.target_client.name == self.name:
                info = self.get_torrent_info(torrent)
                if not info:
                    logger.debug(f"Torrent {torrent.name} info not found in target rpc_client {self.name}")
                    return TorrentState.ERROR
                
                torrent.set_target_client_info(info)
                try:
                    state_name = f"TARGET_{info['state'].upper()}"
                    return TorrentState[state_name]
                except (KeyError, AttributeError) as e:
                    logger.error(f"Invalid state for torrent {torrent.name}: {info.get('state', 'None')}")
                    return TorrentState.ERROR
            
            return TorrentState.UNCLAIMED
        except Exception as e:
            logger.error(f"Error getting torrent state for {torrent.name} on {self.name}: {e}")
            return TorrentState.ERROR
    
    def remove_torrent(self, torrent_id, remove_data=True):
        with self._lock:
            if not self.ensure_connected():
                raise ConnectionError(f"Not connected to {self.name} deluge")
            
            try:
                logger.debug(f"Removing torrent {torrent_id} from {self.name}")
                if self.connection_type == "web":
                    self._send_web_request(
                        "core.remove_torrent",
                        [torrent_id, remove_data],
                        id=3
                    )
                else:
                    self.rpc_client.core.remove_torrent(torrent_id, remove_data)
            except Exception as e:
                logger.error(f"Error removing torrent {torrent_id} from {self.name}: {e}")
                raise

    def get_all_torrents_status(self):
        """
        Safely get and decode status of all torrents.
        Returns a dictionary of torrents with their statuses.
        """
        with self._lock:
            if not self.ensure_connected():
                logger.warning(f"Cannot get torrents status: not connected to {self.name}")
                return {}
            
            try:
                # Use a minimal set of fields to reduce memory usage
                # save_path is needed for cross-seed detection in manual transfers
                # time_added is needed to identify the original torrent in cross-seed groups
                # trackers is needed to show tracker names in the transfer modal
                fields = ['name', 'state', 'progress', 'save_path', 'total_size', 'time_added', 'trackers']
                retry_count = 0
                max_retries = 3
                
                while retry_count < max_retries:
                    try:
                        if self.connection_type == "web":
                            result = self._send_web_request(
                                "core.get_torrents_status",
                                [[], fields],
                                id=3
                            )
                            # Handle None response (e.g., during Deluge restart)
                            if result.get('result') is None:
                                logger.debug(f"No torrents data from {self.name} web client")
                                return {}
                            return result['result']
                        else:
                            result = self.rpc_client.core.get_torrents_status({}, fields)
                            return decode_bytes(result) or {}
                    except Exception as e:
                        retry_count += 1
                        if retry_count >= max_retries:
                            raise
                        logger.warning(f"Retrying get_torrents_status for {self.name} after error: {e}")
                        time.sleep(1)
                
                return {}
            except Exception as e:
                logger.error(f"Error getting torrent statuses from {self.name} after {max_retries} attempts: {e}")
                return {}

    def get_default_download_path(self) -> str:
        """Get the default download location configured in Deluge.
        
        Returns:
            Default download path string
            
        Raises:
            ConnectionError: If not connected to Deluge
            Exception: If the API call fails
        """
        with self._lock:
            if not self.ensure_connected():
                raise ConnectionError(f"Not connected to {self.name} deluge")
            
            try:
                if self.connection_type == "web":
                    result = self._send_web_request(
                        "core.get_config_value",
                        ["download_location"],
                        id=3
                    )
                    return result.get("result", "")
                else:
                    result = self.rpc_client.core.get_config_value("download_location")
                    return decode_bytes(result) if result else ""
            except Exception as e:
                logger.error(f"Error getting default download path from {self.name}: {e}")
                raise

    def get_torrent_progress_bytes(self, torrent_hash: str) -> dict:
        """Get torrent download progress in bytes.
        
        Args:
            torrent_hash: The torrent hash to check
            
        Returns:
            Dict with 'total_done' and 'total_size' in bytes
            
        Raises:
            ConnectionError: If not connected to Deluge
            Exception: If torrent not found or API call fails
        """
        with self._lock:
            if not self.ensure_connected():
                raise ConnectionError(f"Not connected to {self.name} deluge")
            
            try:
                fields = ["total_done", "total_size"]
                if self.connection_type == "web":
                    result = self._send_web_request(
                        "core.get_torrent_status",
                        [torrent_hash, fields],
                        id=3
                    )
                    status = result.get("result")
                    if not status:
                        raise Exception(f"Torrent {torrent_hash} not found")
                    return {
                        "total_done": status.get("total_done", 0),
                        "total_size": status.get("total_size", 0)
                    }
                else:
                    status = self.rpc_client.core.get_torrent_status(torrent_hash, fields)
                    status = decode_bytes(status)
                    if not status:
                        raise Exception(f"Torrent {torrent_hash} not found")
                    return {
                        "total_done": status.get("total_done", 0),
                        "total_size": status.get("total_size", 0)
                    }
            except Exception as e:
                logger.error(f"Error getting progress for torrent {torrent_hash} from {self.name}: {e}")
                raise

    def get_magnet_uri(self, torrent_hash: str) -> str:
        """Get the magnet URI for a torrent.
        
        Args:
            torrent_hash: The torrent hash
            
        Returns:
            Magnet URI string
            
        Raises:
            ConnectionError: If not connected to Deluge
            Exception: If torrent not found or API call fails
        """
        with self._lock:
            if not self.ensure_connected():
                raise ConnectionError(f"Not connected to {self.name} deluge")
            
            try:
                if self.connection_type == "web":
                    result = self._send_web_request(
                        "core.get_magnet_uri",
                        [torrent_hash],
                        id=3
                    )
                    magnet = result.get("result")
                    if not magnet:
                        raise Exception(f"Failed to get magnet URI for torrent {torrent_hash}")
                    return magnet
                else:
                    magnet = self.rpc_client.core.get_magnet_uri(torrent_hash)
                    if not magnet:
                        raise Exception(f"Failed to get magnet URI for torrent {torrent_hash}")
                    return decode_bytes(magnet) if isinstance(magnet, bytes) else magnet
            except Exception as e:
                logger.error(f"Error getting magnet URI for torrent {torrent_hash} from {self.name}: {e}")
                raise

    def is_private_torrent(self, torrent_hash: str) -> bool:
        """Check if a torrent has the private flag set.
        
        Uses the all-torrents status query (same pattern as has_torrent and
        get_torrent_info) which is more reliable than the single-torrent
        get_torrent_status lookup that can return empty results.
        
        Private torrents use private trackers and cannot be added via
        magnet links on a different client (the target won't be able to
        reach the private tracker to download metadata).
        
        Args:
            torrent_hash: Hash of the torrent to check
            
        Returns:
            True if the torrent is private, False otherwise
            
        Raises:
            ConnectionError: If not connected to Deluge
            Exception: If API call fails
        """
        with self._lock:
            if not self.ensure_connected():
                raise ConnectionError(f"Not connected to {self.name} deluge")
            
            try:
                fields = ["private"]
                if self.connection_type == "web":
                    result = self._send_web_request(
                        "web.update_ui",
                        [fields, {}],
                        id=3
                    )
                    if not result.get('result') or not result['result'].get('torrents'):
                        return False
                    current_torrents = result['result']['torrents']
                else:
                    current_torrents = decode_bytes(
                        self.rpc_client.core.get_torrents_status({}, fields)
                    )
                    if current_torrents is None:
                        return False
                
                for key in current_torrents:
                    if key.lower() == torrent_hash.lower():
                        return bool(current_torrents[key].get('private', False))
                
                logger.warning(f"Torrent {torrent_hash} not found on {self.name} when checking private flag")
                return False
            except Exception as e:
                logger.error(f"Error checking private flag for {torrent_hash} from {self.name}: {e}")
                raise

    def add_torrent_magnet(self, magnet_uri: str, options: dict = None, label: str = None) -> str:
        """Add a torrent from a magnet URI.
        
        Args:
            magnet_uri: The magnet URI to add
            options: Optional dict of torrent options (download_location, etc.)
            label: Optional label to apply (requires Label plugin)
            
        Returns:
            The torrent hash of the added torrent
            
        Raises:
            ConnectionError: If not connected to Deluge
            Exception: If adding fails
        """
        with self._lock:
            if not self.ensure_connected():
                raise ConnectionError(f"Not connected to {self.name} deluge")
            
            options = options or {}
            
            try:
                if self.connection_type == "web":
                    result = self._send_web_request(
                        "core.add_torrent_magnet",
                        [magnet_uri, options],
                        id=3
                    )
                    torrent_hash = result.get("result")
                    if not torrent_hash:
                        error = result.get("error", {}).get("message", "Unknown error")
                        raise Exception(f"Failed to add magnet: {error}")
                else:
                    torrent_hash = self.rpc_client.core.add_torrent_magnet(magnet_uri, options)
                    if not torrent_hash:
                        raise Exception("Failed to add magnet: no hash returned")
                    torrent_hash = decode_bytes(torrent_hash) if isinstance(torrent_hash, bytes) else torrent_hash
                
                # Apply label if requested
                if label:
                    self._apply_label(torrent_hash, label)
                
                return torrent_hash
            except Exception as e:
                logger.error(f"Error adding magnet to {self.name}: {e}")
                raise

    @staticmethod
    def _calculate_create_timeout(total_size: int) -> int:
        """Calculate polling timeout for create_torrent based on file size.
        
        Deluge must SHA1-hash every byte with 256KB pieces before the torrent
        appears in the session. Timeout scales with size, with generous margins
        for slow/network-attached storage.
        
        Args:
            total_size: Total file size in bytes (0 = unknown)
            
        Returns:
            Timeout in seconds (minimum 30, maximum 600)
        """
        if total_size <= 0:
            return 240  # Unknown size: use generous default
        
        gb = total_size / (1024 ** 3)
        
        if gb <= 0.1:       # ≤100MB — tiny, hash is near-instant
            return 30
        elif gb <= 1:       # ≤1GB
            return 60
        elif gb <= 10:      # ≤10GB
            return 120
        elif gb <= 50:      # ≤50GB
            return 240
        else:               # >50GB — very large
            return 600

    def start_create_torrent(
        self,
        path: str,
        trackers: list[str],
        private: bool = True,
        add_to_session: bool = True,
        label: str = None,
        total_size: int = 0
    ) -> dict:
        """Fire the Deluge create_torrent RPC and return a poll spec.
        
        Issues the RPC call then returns immediately.  Deluge 2.1.x hashes the
        files asynchronously; the caller must use :meth:`poll_created_torrent`
        to discover the info hash once hashing completes.
        
        Args:
            path: Path to the file or directory to create torrent from
            trackers: List of tracker URLs (embedded in torrent; also used to
                identify it during polling)
            private: Whether to create a private torrent (disables DHT/PEX)
            add_to_session: Whether to add the created torrent to Deluge
            label: Optional label to apply when the torrent is found by poll
            total_size: Total size in bytes for dynamic timeout (0 = unknown)
            
        Returns:
            Poll spec dict with keys:
            - ``expected_name`` (str): basename of *path* — the name Deluge
              will assign to the torrent
            - ``tracker_urls`` (list[str]): tracker URLs to match against
            - ``timeout`` (int): seconds before the caller should give up
            
        Raises:
            ConnectionError: If not connected to Deluge
            Exception: If the RPC call itself fails
        """
        import os
        import time
        import tempfile
        
        with self._lock:
            if not self.ensure_connected():
                raise ConnectionError(f"Not connected to {self.name} deluge")
            
            piece_length = 262144  # 256KB pieces
            tracker = trackers[0] if trackers else ""
            # Deluge expects trackers as list of lists (tiers), not a flat list.
            # Put all URLs in the same tier so clients try them in parallel.
            tracker_tiers = [trackers] if trackers else []
            # Use system temp directory - works on both Docker and bare-metal installs
            target = os.path.join(tempfile.gettempdir(), f"transfer_{int(time.time() * 1000)}.torrent")
            
            expected_name = os.path.basename(path.rstrip('/'))
            
            logger.debug(
                f"Creating transfer torrent for '{expected_name}' on {self.name}"
            )
            logger.debug(
                f"start_create_torrent params: path={path}, tracker={tracker}, "
                f"piece_length={piece_length}, target={target}, private={private}, "
                f"tracker_tiers={tracker_tiers}, add_to_session={add_to_session}"
            )
            
            try:
                if self.connection_type == "web":
                    create_result = self._send_web_request(
                        "core.create_torrent",
                        [
                            path,           # path
                            tracker,        # tracker (primary)
                            piece_length,   # piece_length
                            "",             # comment
                            target,         # target file path
                            [],             # webseeds
                            private,        # private
                            "transferarr",  # created_by
                            tracker_tiers,
                            add_to_session  # add_to_session
                        ],
                        id=3
                    )
                    api_error = create_result.get("error")
                    logger.debug(f"web create_torrent response: {create_result}")
                    
                    if api_error:
                        error_msg = api_error.get("message", str(api_error)) if isinstance(api_error, dict) else str(api_error)
                        raise Exception(f"Deluge create_torrent failed: {error_msg}")
                else:
                    create_result = self.rpc_client.core.create_torrent(
                        path,           # path
                        tracker,        # tracker (primary)
                        piece_length,   # piece_length
                        "",             # comment
                        target,         # target file path
                        [],             # webseeds
                        private,        # private
                        "transferarr",  # created_by
                        tracker_tiers,
                        add_to_session  # add_to_session
                    )
                    logger.debug(f"rpc create_torrent response: {create_result}")
            except Exception as e:
                logger.error(f"Error creating torrent on {self.name}: {e}")
                raise
        
        timeout = self._calculate_create_timeout(total_size)
        size_label = f"{total_size / (1024**3):.1f}GB" if total_size > 0 else "unknown size"
        logger.debug(
            f"RPC fired for '{expected_name}' (timeout {timeout}s for {size_label})"
        )
        
        return {
            "expected_name": expected_name,
            "tracker_urls": list(trackers) if trackers else [],
            "timeout": timeout,
        }

    def poll_created_torrent(
        self,
        expected_name: str,
        tracker_urls: list[str],
        label: str = None
    ) -> str | None:
        """Perform one non-blocking check for a created torrent.
        
        Queries Deluge for all torrents and scans for one whose name matches
        *expected_name* and whose tracker URLs overlap with *tracker_urls*.
        This is idempotent and cross-seed safe.
        
        Args:
            expected_name: The torrent name to look for (basename of path)
            tracker_urls: Our tracker URLs to match against
            label: Optional label to apply if the torrent is found
            
        Returns:
            The info hash if found, None otherwise
        """
        our_tracker_urls = set(tracker_urls) if tracker_urls else set()
        
        with self._lock:
            if not self.ensure_connected():
                raise ConnectionError(f"Not connected to {self.name} deluge")
            
            if self.connection_type == "web":
                result = self._send_web_request(
                    "web.update_ui",
                    [["name", "trackers"], {}],
                    id=3
                )
                torrents = result.get('result', {}).get('torrents', {})
            else:
                torrents = decode_bytes(
                    self.rpc_client.core.get_torrents_status({}, ['name', 'trackers'])
                )
        
        for torrent_hash, info in torrents.items():
            torrent_name = info.get('name', '')
            if torrent_name != expected_name:
                continue
            
            torrent_trackers = info.get('trackers', []) or []
            torrent_urls = {
                t.get('url', '') if isinstance(t, dict) else ''
                for t in torrent_trackers
            }
            
            if our_tracker_urls & torrent_urls:
                logger.debug(
                    f"Created torrent found: {expected_name} "
                    f"(hash: {torrent_hash[:8]}...)"
                )
                if label:
                    with self._lock:
                        self._apply_label(torrent_hash, label)
                return torrent_hash
        
        return None

    def get_transfer_progress(self, torrent_hash: str) -> dict:
        """Get download progress for a transfer torrent.
        
        Args:
            torrent_hash: Hash of the torrent to check
            
        Returns:
            dict with keys: total_done, total_size, state, progress, download_payload_rate
            Returns empty dict if torrent not found or error
        """
        with self._lock:
            if not self.ensure_connected():
                logger.warning(f"Cannot get progress: not connected to {self.name}")
                return {}
            
            try:
                fields = [
                    'total_done', 'total_size', 'state', 'progress',
                    'download_payload_rate', 'num_seeds', 'num_peers'
                ]
                
                if self.connection_type == "web":
                    result = self._send_web_request(
                        "core.get_torrent_status",
                        [torrent_hash, fields],
                        id=3
                    )
                    status = result.get('result', {})
                else:
                    status = decode_bytes(
                        self.rpc_client.core.get_torrent_status(torrent_hash, fields)
                    )
                
                if not status:
                    logger.debug(f"No status found for torrent {torrent_hash[:8]}... on {self.name}")
                    return {}
                
                return status
                
            except Exception as e:
                logger.error(f"Error getting progress for {torrent_hash[:8]}... on {self.name}: {e}")
                return {}

    def force_reannounce(self, torrent_hash: str) -> bool:
        """Force the torrent to re-announce to trackers.
        
        This can help with peer discovery if the download has stalled.
        
        Args:
            torrent_hash: Hash of the torrent to re-announce
            
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            if not self.ensure_connected():
                logger.warning(f"Cannot reannounce: not connected to {self.name}")
                return False
            
            try:
                logger.debug(f"Forcing re-announce for {torrent_hash[:8]}... on {self.name}")
                
                if self.connection_type == "web":
                    self._send_web_request(
                        "core.force_reannounce",
                        [[torrent_hash]],
                        id=3
                    )
                else:
                    self.rpc_client.core.force_reannounce([torrent_hash])
                
                return True
                
            except Exception as e:
                logger.error(f"Error forcing reannounce for {torrent_hash[:8]}... on {self.name}: {e}")
                return False

    def force_recheck(self, torrent_hash: str) -> bool:
        """Force the torrent to recheck its files on disk.
        
        This is useful when files already exist (e.g., after a transfer torrent
        download) and we want Deluge to verify them instead of re-downloading.
        
        Args:
            torrent_hash: Hash of the torrent to recheck
            
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            if not self.ensure_connected():
                logger.warning(f"Cannot recheck: not connected to {self.name}")
                return False
            
            try:
                logger.info(f"Forcing recheck for {torrent_hash[:8]}... on {self.name}")
                
                if self.connection_type == "web":
                    self._send_web_request(
                        "core.force_recheck",
                        [[torrent_hash]],
                        id=3
                    )
                else:
                    self.rpc_client.core.force_recheck([torrent_hash])
                
                return True
                
            except Exception as e:
                logger.error(f"Error forcing recheck for {torrent_hash[:8]}... on {self.name}: {e}")
                return False

    def resume_torrent(self, torrent_hash: str) -> bool:
        """Resume a paused torrent.
        
        Args:
            torrent_hash: Hash of the torrent to resume
            
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            if not self.ensure_connected():
                logger.warning(f"Cannot resume: not connected to {self.name}")
                return False
            
            try:
                logger.debug(f"Resuming torrent {torrent_hash[:8]}... on {self.name}")
                
                if self.connection_type == "web":
                    self._send_web_request(
                        "core.resume_torrent",
                        [[torrent_hash]],
                        id=3
                    )
                else:
                    self.rpc_client.core.resume_torrent([torrent_hash])
                
                return True
                
            except Exception as e:
                logger.error(f"Error resuming torrent {torrent_hash[:8]}... on {self.name}: {e}")
                return False

    def test_connection(self):
        """Test the connection to the deluge rpc_client.
        
        Returns:
            dict: A dict with 'success' indicating if connection succeeded and 'message' with details
        """
        try:
            if not self.is_connected():
                try:
                    self._connect(handle_exception=False)
                except Exception as e:
                    logger.info(f"Connection test failed: {str(e)}")
                    return {
                        "success": False,
                        "message": f"Connection failed: {str(e)}"
                    }
            
            # If we got here, we're connected. Test a simple API call
            # self.rpc_client.daemon.info()
            
            return {
                "success": True,
                "message": "Connection successful"
            }
        except Exception as e:
            logger.error(f"Error testing connection to {self.name}: {e}")
            return {
                "success": False,
                "message": f"Error: {str(e)}"
            }
