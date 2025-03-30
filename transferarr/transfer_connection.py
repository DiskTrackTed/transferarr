import logging
from pathlib import Path
from transferarr.utils import get_paths_to_copy
from transferarr.torrent import TorrentState
from transferarr.transfer_client import get_transfer_client

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
        self.transfer_client = None
        self.setup_transfer_clients()
    
    def setup_transfer_clients(self):
        from_config = self.config["transfer_config"]["from"]
        to_config = self.config["transfer_config"]["to"]
        self.transfer_client = get_transfer_client(from_config, to_config)

    
    def do_copy_torrent(self, torrent):
        ## Copy .torrent file to tmp dir
        torrent.state = TorrentState.COPYING
        dot_torrent_file_path = str(Path(self.source_dot_torrent_path).joinpath(f"{torrent.id}.torrent"))


        file_dump = self.transfer_client.get_dot_torrent_file_dump(dot_torrent_file_path)

        success = self.transfer_client.upload(dot_torrent_file_path, self.destination_dot_torrent_tmp_dir)
        if not success:
            torrent.state = TorrentState.ERROR
            logger.error(f"Failed to copy .torrent file: {dot_torrent_file_path}")
            return
        dest_dot_torrent_path = self.destination_dot_torrent_tmp_dir + f"{id}.torrent"
        paths_to_copy = get_paths_to_copy(torrent)
        for path in paths_to_copy:
            source_file_path = str(Path(self.source_torrent_download_path).joinpath(Path(path)))
            destination = self.destination_torrent_download_path

            success = self.transfer_client.upload(source_file_path, destination)
            if success:
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

    def upload(self, source, destination):
        """Upload a file to the destination using the transfer clients."""