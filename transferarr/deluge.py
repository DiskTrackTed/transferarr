import logging
import threading
import time
from transferarr.utils import decode_bytes
from deluge_client import DelugeRPCClient
from transferarr.torrent import TorrentState

logger = logging.getLogger(__name__)

class DelugeClient:
    def __init__(self, name, host, port, username, password):
        self.name = name
        self.type = "deluge"
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        self.torrent_download_path = None
        self.dot_torrent_path = None
        self.dot_torrent_tmp_dir = None
        self.transfer_client = None
        self.connections = []
        self._lock = threading.RLock()  # Use reentrant lock for thread safety
        self._connect()
    
    def _connect(self, handle_exception=True):
        """Connect to the Deluge client with proper error handling"""
        try:
            self.client = DelugeRPCClient(
                host=self.host, 
                port=self.port, 
                username=self.username, 
                password=self.password,
                automatic_reconnect=True
            )
            self.client.connect()
            if self.client.connected:
                logger.info(f"Connected to {self.name} deluge on {self.host}:{self.port}")
            else:
                logger.error(f"Failed to connect to {self.name} deluge on {self.host}:{self.port}")
        except Exception as e:
            if handle_exception:
                logger.error(f"Error connecting to {self.name} deluge: {e}")
            else:
                raise e
            # logger.error(f"Error connecting to {self.name} deluge: {e}")
            # self.client = None

    def ensure_connected(self):
        """Ensure client is connected, reconnect if needed"""
        with self._lock:
            if not self.client or not self.is_connected():
                logger.info(f"Reconnecting to {self.name} deluge...")
                self._connect()
            return self.is_connected()

    def add_torrent_file(self, torrent_file_path, torrent_file_data, options):
        with self._lock:
            if not self.ensure_connected():
                raise ConnectionError(f"Not connected to {self.name} deluge")
            try:
                self.client.core.add_torrent_file(torrent_file_path, torrent_file_data, options)
            except Exception as e:
                logger.error(f"Error adding torrent file: {e}")
                raise

    def add_connection(self, connection):
        self.connections.append(connection)

    def remove_connection(self, connection):
        self.connections.remove(connection)

    def is_connected(self):
        try:
            return self.client and self.client.connected
        except:
            return False
    
    def has_torrent(self, torrent):
        with self._lock:
            if not self.ensure_connected():
                return False
            try:
                current_torrents = decode_bytes(self.client.core.get_torrents_status({}, ['name']))
                for key in current_torrents:
                    # print(f"Looking for: {torrent.name}, found: {current_torrents[key]['name']}")
                    if current_torrents[key]['name'] == torrent.name:
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
                current_torrents = decode_bytes(
                    self.client.core.get_torrents_status({}, [
                        'name', 'state', 'files', 'progress','total_size'
                        ]))
                for key in current_torrents:
                    if current_torrents[key]['name'] == torrent.name:
                        torrent.id = key
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
                    logger.debug(f"Torrent {torrent.name} info not found in home client {self.name}")
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
                    logger.debug(f"Torrent {torrent.name} info not found in target client {self.name}")
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
                self.client.core.remove_torrent(torrent_id, remove_data)
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
                        result = self.client.core.get_torrents_status({}, fields)
                        decoded = decode_bytes(result)
                        
                        # Create a new dictionary with just the fields we need
                        filtered = {}
                        for torrent_id, torrent_data in decoded.items():
                            filtered[torrent_id] = {
                                'name': torrent_data.get('name', ''),
                                'state': torrent_data.get('state', ''),
                                'progress': torrent_data.get('progress', 0)
                            }
                        return filtered
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
        """Test the connection to the deluge client.
        
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
            self.client.daemon.info()
            
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

def get_local_deluge_info(local_client, torrents):
    items = local_client.client.core.get_torrents_status({}, [])
    decoded_dict = decode_bytes(items)
    for key in decoded_dict:
        match = None
        for torrent in torrents:
            if decoded_dict[key]['name'] == torrent.name:
                match = torrent
                break
        if match:
            match.id = key
            match.home_client_info = decoded_dict[key]
    return torrents

def get_sb_deluge_info(sb_client, torrents):
    items = sb_client.client.core.get_torrents_status({}, [])
    decoded_dict = decode_bytes(items)
    for key in decoded_dict:
        match = None
        for torrent in torrents:
            if decoded_dict[key]['name'] == torrent.name:
                match = torrent
                break
        if match:
            match.target_client_info = decoded_dict[key]
    return torrents