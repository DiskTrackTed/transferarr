from utils import decode_bytes
from deluge_client import DelugeRPCClient

class DelugeClient:
    client = None
    torrent_download_path = None
    dot_torrent_path = None
    dot_torrent_tmp_dir = None
    def __init__(self, host, port, username, password, dot_torrent_path=None, dot_torrent_tmp_dir=None, torrent_download_path=None):
        self.torrent_download_path = torrent_download_path
        self.dot_torrent_path = dot_torrent_path
        self.dot_torrent_tmp_dir = dot_torrent_tmp_dir
        self.client = DelugeRPCClient(host=host, port=port, username=username, password=password)
        self.client.connect()

    def is_connected(self):
        return self.client.connected

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
            match.local_deluge_info = decoded_dict[key]
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
            match.sb_deluge_info = decoded_dict[key]
    return torrents 