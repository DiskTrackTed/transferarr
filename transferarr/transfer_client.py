import logging
import os
import traceback
import time
import uuid
# from tqdm import tqdm
from tqdm_loggable.auto import tqdm
from base64 import b64encode
from abc import ABC
from transferarr.ftp import SFTPClient

logger = logging.getLogger(__name__)

class TransferClient(ABC):
    def __init__(self):
        pass

class LocalStorageClient(TransferClient):
    def __init__(self):
        pass


class LocalAndSFTPClient(TransferClient):

    def __init__(self, sftp_config, target_type="sftp"):
        self. target_type = target_type
        self.sftp_client = SFTPClient(**sftp_config)

    def get_dot_torrent_file_dump(self, dot_torrent_file_path):
        if self.target_type == "sftp":
            logger.debug(f"Getting .torrent file dump from {dot_torrent_file_path}")

            with open(str(dot_torrent_file_path), 'rb') as f:
                data = f.read()
                return b64encode(data)
        else:
            self.sftp_client.open_connection()
            logger.debug(f"Getting .torrent file dump from {self.sftp_client.host}:{dot_torrent_file_path}")
            # print(self.source_sftp_client.connection.listdir("/closet-deluge/state"))
            with self.sftp_client.connection.open(str(dot_torrent_file_path), 'rb') as f:
                data = f.read()
                self.sftp_client.close()
                return b64encode(data)


class SFTPAndSFTPClient(TransferClient):

    def __init__(self, source_sftp_config, target_sftp_config):
        self.source_sftp_client = SFTPClient(**source_sftp_config)
        self.target_sftp_client = SFTPClient(**target_sftp_config)
        self.current_progress = {}

    def get_dot_torrent_file_dump(self, dot_torrent_file_path):
        self.source_sftp_client.open_connection()
        logger.debug(f"Getting .torrent file dump from {self.source_sftp_client.host}:{dot_torrent_file_path}")
        # print(self.source_sftp_client.connection.listdir("/closet-deluge/state"))
        with self.source_sftp_client.connection.open(str(dot_torrent_file_path), 'rb') as f:
            data = f.read()
            self.source_sftp_client.close()
            return b64encode(data)

    def count_files(self, source_path):
        """Count the total number of files that need to be copied"""
        try:
            file_count = 0
            
            def count_recursively(path):
                nonlocal file_count
                if self.source_sftp_client.connection.isfile(path):
                    file_count += 1
                elif self.source_sftp_client.connection.isdir(path):
                    for item in self.source_sftp_client.connection.listdir(path):
                        count_recursively(os.path.join(path, item))
            
            count_recursively(source_path)
            return file_count
        except Exception as e:
            logger.error(f"Error counting files: {e}")
            return 0

    def upload(self, source_path, target_path, torrent):
        logger.debug(f"Uploading {self.source_sftp_client.host}:{source_path} to {self.target_sftp_client.host}:{target_path}")
        try:
            self.source_sftp_client.open_connection()
            self.target_sftp_client.open_connection()
            target_path = os.path.join(target_path, os.path.basename(source_path))
            
            # Count total files before starting the transfer
            total_files = self.count_files(source_path)
            torrent.total_files = total_files
            torrent.current_file_count = 0
            
            if self.source_sftp_client.connection.isfile(source_path):
                self.upload_file(source_path, target_path, torrent)
            else:
                self.upload_directory(source_path, target_path, torrent)
            return True
        except Exception as e:
            logger.error(f"FTP upload failed: {e}")
            traceback.print_exc()
            return False
        finally:
            self.source_sftp_client.close()
            self.target_sftp_client.close()
    
    def upload_directory(self, source_path, target_path, torrent):
        """
        Upload a file from local storage to SFTP server
        """
        """Stream file directly between servers without full download"""
        try:
            self.target_sftp_client.connection.makedirs(target_path)
        except OSError:
            pass  # Directory exists

        print(self.source_sftp_client.connection.listdir(source_path))
        for item in self.source_sftp_client.connection.listdir(source_path):
        # for item in os.listdir(local_dir):
            source_path_tmp = os.path.join(source_path, item)
            target_path_tmp = os.path.join(target_path, item)

            print(source_path_tmp)
            print(target_path_tmp)
            
            if self.source_sftp_client.connection.isfile(source_path_tmp):
                self.upload_file(source_path_tmp, target_path_tmp, torrent)
            elif self.source_sftp_client.connection.isdir(source_path_tmp):
                self.upload_directory(source_path_tmp, target_path_tmp, torrent)

    def upload_file(self, source_path, target_path, torrent):
        try:
            logger.debug(f"Uploading {self.source_sftp_client.host}:{source_path} to {self.target_sftp_client.host}:{target_path}")
            random_id = str(uuid.uuid4())
            tmp_file_path = os.path.join("/tmp", f"transferarr-{random_id}.tmp")
            file_size = self.source_sftp_client.connection.stat(source_path).st_size
            
            # Set the current file name in the torrent
            file_name = os.path.basename(source_path)
            torrent.current_file = file_name
            torrent.progress = 0
            torrent.current_file_count += 1

            # def download_callback(sent, total):
            #     torrent.progress = sent / file_size * 50

            logger.debug(f"Downloading {source_path} to {tmp_file_path}")
            # self.source_sftp_client.connection.get(source_path, tmp_file_path, callback=download_callback)
            self.source_sftp_client.connection.get(source_path, tmp_file_path)

            def upload_callback(sent, total):
                torrent.progress = sent / file_size * 100

            logger.debug(f"Uploading {tmp_file_path} to {target_path}")
            self.target_sftp_client.connection.put(tmp_file_path, target_path, callback=upload_callback)

            os.remove(tmp_file_path)
            torrent.progress = 100  # Mark progress as complete
            return True
        except Exception as e:
            logger.error(f"FTP upload failed: {e}")
            traceback.print_exc()
            torrent.progress = 0  # Reset progress on failure
            return False
    

def get_transfer_client(from_config,to_config):
    from_connection_type = from_config.get('type')
    to_connection_type = to_config.get('type')
    if from_connection_type == 'sftp':
        if to_connection_type == 'sftp':
            return SFTPAndSFTPClient(from_config["sftp"], to_config["sftp"])
        else:
            logger.error(f"Invalid connection type for target client: {to_connection_type}")
            return None
    else:
        logger.error(f"Invalid connection type for from client: {from_connection_type}")
        return None


