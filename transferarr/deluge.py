import logging
from transferarr.utils import decode_bytes
from transferarr.ftp import SFTPClient
from deluge_client import DelugeRPCClient
from transferarr.torrent import TorrentState

logger = logging.getLogger(__name__)

class DelugeClient:
    client = None
    name = None
    torrent_download_path = None
    dot_torrent_path = None
    dot_torrent_tmp_dir = None
    transfer_client = None
    connections = []
    def __init__(self, name, host, port, username, password):
        self.name = name
        self.client = DelugeRPCClient(host=host, port=port, username=username, password=password)
        self.client.connect()
        if(self.client.connected):
            logger.info(f"Connected to {name} deluge on {host}:{port}")
        else:
            logger.error(f"Failed to connect to {name} deluge on {host}:{port}")


    def add_torrent_file(self, torrent_file_path, torrent_file_data, options):
        self.client.core.add_torrent_file(torrent_file_path, torrent_file_data, options)

    def add_connection(self, connection):
        self.connections.append(connection)

    def remove_connection(self, connection):
        self.connections.remove(connection)

    def is_connected(self):
        return self.client.connected
    
    def has_torrent(self, torrent):
        current_torrents = decode_bytes(self.client.core.get_torrents_status({}, ['name']))
        for key in current_torrents:
            if current_torrents[key]['name'] == torrent.name:
                return True
        return False
    
    def get_torrent_info(self, torrent):
        current_torrents = decode_bytes(self.client.core.get_torrents_status({}, ['name', 'state','files']))
        for key in current_torrents:
            if current_torrents[key]['name'] == torrent.name:
                torrent.id = key
                return current_torrents[key]
        return None
    
    def get_torrent_state(self, torrent):
        if torrent.home_client.name == self.name:
            try :
                torrent.home_client_info = self.get_torrent_info(torrent)
                torrent_state = TorrentState[f"HOME_{torrent.home_client_info['state'].upper()}"]
                return torrent_state
            except Exception as e:
                logging.error(f"Failed to get torrent state for {torrent.name} on {self.name}")
                logging.error(e)
                return TorrentState.ERROR
        elif torrent.target_client.name == self.name:
            try :
                torrent.target_client_info = self.get_torrent_info(torrent)
                torrent_state = TorrentState[f"TARGET_{torrent.target_client_info['state'].upper()}"]
                return torrent_state
            except Exception as e:
                logging.error(f"Failed to get torrent state for {torrent.name} on {self.name}")
                logging.error(e)
                return TorrentState.ERROR
        return TorrentState.UNCLAIMED
    
    def remove_torrent(self, torrent_id, remove_data=True):
        self.client.core.remove_torrent(torrent_id, remove_data)




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