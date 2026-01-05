import logging
import threading
import time
import requests
from transferarr.utils import decode_bytes
from deluge_client import DelugeRPCClient
from transferarr.models.torrent import TorrentState

logger = logging.getLogger(__name__)

class DelugeClient:
    def __init__(self, name, host, port, password, username=None, connection_type="rpc"):
        self.type = "deluge"
        self.name = name
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.connection_type = connection_type
        self.rpc_client = None
        self.connections = []
        self._lock = threading.RLock()
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
                    logger.info(f"Reconnecting to {self.name} deluge...")
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

    def add_torrent_file(self, torrent_file_path, torrent_file_data, options):
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
                    if not result.get("result"):
                        logger.error(f"Failed to add torrent file via web: {result.get('error', 'Unknown error')}")
                        raise Exception(f"Web client error: {result.get('error', 'Unknown error')}")
                elif self.connection_type == "rpc":
                    self.rpc_client.core.add_torrent_file(torrent_file_path, torrent_file_data, options)
            except Exception as e:
                logger.error(f"Error adding torrent file: {e}")
                raise e

    def add_connection(self, connection):
        self.connections.append(connection)

    def remove_connection(self, connection):
        self.connections.remove(connection)

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
                    current_torrents = result['result']['torrents']
                else:
                    current_torrents = decode_bytes(self.rpc_client.core.get_torrents_status({}, ['name']))
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
                        [["name", "state", "files", "progress", "total_size"], {}],
                        id=3
                    )
                    current_torrents = result['result']['torrents']
                else:
                    current_torrents = decode_bytes(
                        self.rpc_client.core.get_torrents_status({}, [
                            'name', 'state', 'files', 'progress','total_size'
                            ]))
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
                
                torrent.home_client_info = info
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
                
                torrent.target_client_info = info
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
                fields = ['name', 'state', 'progress']
                retry_count = 0
                max_retries = 3
                
                while retry_count < max_retries:
                    try:
                        if self.connection_type == "web":
                            return self._send_web_request(
                                "core.get_torrents_status",
                                [[], fields],
                                id=3
                            )['result']
                        else:
                            result = self.rpc_client.core.get_torrents_status({}, fields)
                            return decode_bytes(result)
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
