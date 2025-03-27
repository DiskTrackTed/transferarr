import logging
from transferarr.utils import decode_bytes
from transferarr.ftp import SFTPClient
from deluge_client import DelugeRPCClient

logger = logging.getLogger(__name__)

class DelugeClient:
    client = None
    torrent_download_path = None
    dot_torrent_path = None
    dot_torrent_tmp_dir = None
    transfer_client = None
    def __init__(self, host, port, username, password, 
                 dot_torrent_path=None, 
                 dot_torrent_tmp_dir=None, 
                 torrent_download_path=None,
                 transfer_config=None):
        self.torrent_download_path = torrent_download_path
        self.dot_torrent_path = dot_torrent_path
        self.dot_torrent_tmp_dir = dot_torrent_tmp_dir
        self.transfer_config = transfer_config
        self.client = DelugeRPCClient(host=host, port=port, username=username, password=password)
        self.client.connect()
        self.setup_transfer_client()

    def is_connected(self):
        return self.client.connected
    
    def setup_transfer_client(self):
        if self.transfer_config is None:
            logger.warning("Transfer config is None")
            return
        if self.transfer_config.get('type') == 'ftp':
            ftp_config = self.transfer_config.get('ftp')
            if ftp_config.get('use_ssh_config'):
                self.transfer_client = SFTPClient(
                    ssh_config_file=ftp_config.get('ssh_config_file'),
                    ssh_config_host=ftp_config.get('ssh_config_host')
                )

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