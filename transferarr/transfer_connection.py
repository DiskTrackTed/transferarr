import logging
from base64 import b64encode
from pathlib import Path
from transferarr.utils import get_paths_to_copy
from transferarr.ftp import SFTPClient
from transferarr.torrent import TorrentState

logger = logging.getLogger(__name__)

class TransferConnection:
    def __init__(self, config, from_client, to_client):
        self.config = config
        self.source_dot_torrent_path = config.get("source_dot_torrent_path")
        self.source_torrent_download_path = config.get("source_torrent_download_path")
        self.destination_dot_torrent_tmp_dir = config.get("destination_dot_torrent_tmp_dir")
        self.destination_torrent_download_path = config.get("destination_torrent_download_path")
        self.from_client = from_client
        self.to_client = to_client
        self.setup_transfer_client()
    
    def setup_transfer_client(self):
        connection_type = self.config["transfer_config"].get('type')
        if connection_type == 'ftp':
            ftp_config = self.config["transfer_config"].get('ftp')
            if ftp_config.get('use_ssh_config'):
                self.transfer_client = SFTPClient(
                    ssh_config_file=ftp_config.get('ssh_config_file'),
                    ssh_config_host=ftp_config.get('ssh_config_host')
                )
        else:
            logger.error(f"Unknown transfer type: {connection_type}")
        return
    
    def do_copy_torrent(self, torrent):
        ## Copy .torrent file to tmp dir
        torrent.state = TorrentState.COPYING
        dot_torrent_file_path = str(Path(self.source_dot_torrent_path).joinpath(f"{torrent.id}.torrent"))

        if not Path(dot_torrent_file_path).exists():
            torrent.state = TorrentState.ERROR
            logger.error(f"Dot torrent file does not exist: {dot_torrent_file_path}")

        with open(str(dot_torrent_file_path), 'rb') as f:
            data = f.read()
            file_dump = b64encode(data)
        # transfer_file_scp_cli(dot_torrent_file_path, 'sb-2', sb_client.dot_torrent_tmp_dir)
        self.transfer_client.upload(dot_torrent_file_path, self.destination_dot_torrent_tmp_dir)
        dest_dot_torrent_path = self.destination_dot_torrent_tmp_dir + f"{id}.torrent"
        paths_to_copy = get_paths_to_copy(torrent)
        for path in paths_to_copy:
            source_file_path = str(Path(self.source_torrent_download_path).joinpath(Path(path)))
            ftp_destination = self.destination_torrent_download_path
            logger.debug(f"Copying: {source_file_path} to {self.transfer_client.host}:{ftp_destination}")

            success = self.transfer_client.upload(source_file_path, ftp_destination)
            if success == True:
                torrent.state = TorrentState.COPIED
            else:
                torrent.state = TorrentState.ERROR
        if torrent.state == TorrentState.COPIED:
            try:
                self.to_client.add_torrent_file(dest_dot_torrent_path, file_dump, {})
                self.to_client_info = self.to_client.get_torrent_info(torrent)
                torrent.state = self.to_client.get_torrent_state(torrent)
                logger.info(f"Torrent added successfully: {torrent.name}")
            except Exception as e:
                logger.error(f"Error adding torrent: {e}")
                torrent.state = TorrentState.ERROR