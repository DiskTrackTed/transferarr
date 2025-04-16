import logging
import os
import traceback
import time
import uuid
from base64 import b64encode
from abc import ABC
from transferarr.clients.ftp import SFTPClient
from transferarr.exceptions import TrasnferClientException

logger = logging.getLogger(__name__)

class TransferClient(ABC):
    def __init__(self):
        pass

class LocalStorageClient(TransferClient):
    def __init__(self):
        pass


class LocalAndSFTPClient(TransferClient):

    def __init__(self, sftp_config, source_type="local"):
        self.source_type = source_type
        self.sftp_client = SFTPClient(**sftp_config)

    def _init_sftp_client(self, sftp_config):
        try:
            self.sftp_client = SFTPClient(**sftp_config)
        except Exception as e:
            raise TrasnferClientException(f"Failed to initialize SFTP client: {e}") from e

    def test_connection(self):
        """Test the connection to the SFTP server"""
        try:
            self.sftp_client.open_connection()
            return {"success": True, "message": "Connection successful"}
        except Exception as e:
            logger.debug(f"Connection test failed: {e}")
            return {"success": False, "message": str(e)}
        finally:
            self.sftp_client.close()

    def get_dot_torrent_file_dump(self, dot_torrent_file_path):
        if self.source_type == "local":
            logger.debug(f"Getting .torrent file dump from {dot_torrent_file_path}")

            with open(str(dot_torrent_file_path), 'rb') as f:
                data = f.read()
                return b64encode(data)
        else:
            self.sftp_client.open_connection()
            logger.debug(f"Getting .torrent file dump from {self.sftp_client.host}:{dot_torrent_file_path}")
            with self.sftp_client.connection.open(str(dot_torrent_file_path), 'rb') as f:
                data = f.read()
                self.sftp_client.close()
                return b64encode(data)
            
    def count_files(self, source_path):
        """Count the total number of files that need to be copied"""
        if self.source_type == "local":
            return local_count_files(source_path)
        else:
            return sftp_count_files(self.sftp_client, source_path)
        
    def upload(self, source_path, target_path, torrent):
        logger.debug(f"Starting transfer of {source_path} to {target_path}")
        # logger.debug(f"Uploading {self.sftp_client.host}:{source_path} to {self.target_sftp_client.host}:{target_path}")
        try:
            self.sftp_client.open_connection()
            target_path = os.path.join(target_path, os.path.basename(source_path))
            
            # Count total files before starting the transfer
            total_files = self.count_files(source_path)
            torrent.total_files = total_files
            torrent.current_file_count = 0
            
            if self.source_type == "local":
                if os.path.isfile(source_path):
                    self.upload_file(source_path, target_path, torrent)
                else:
                    self.upload_directory(source_path, target_path, torrent)
            else:
                if self.sftp_client.connection.isfile(source_path):
                    self.upload_file(source_path, target_path, torrent)
                else:
                    self.upload_directory(source_path, target_path, torrent)
            return True
        except Exception as e:
            logger.error(f"FTP upload failed: {e}")
            traceback.print_exc()
            return False
        finally:
            self.sftp_client.close()

    def upload_directory(self, source_path, target_path, torrent):
        """
        Upload a file from local storage to SFTP server
        """
        try:
            if self.source_type == "local":
                self.sftp_client.connection.makedirs(target_path)
            else:
                os.makedirs(target_path)
        except OSError:
            pass  # Directory exists

        dirs = os.listdir(source_path) if self.source_type == "local" else self.sftp_client.connection.listdir(source_path)

        for item in dirs:
            source_path_tmp = os.path.join(source_path, item)
            target_path_tmp = os.path.join(target_path, item)

            is_file = os.path.isfile(source_path_tmp) if self.source_type == "local" else self.sftp_client.connection.isfile(source_path_tmp)
            
            if is_file:
                self.upload_file(source_path_tmp, target_path_tmp, torrent)
            else:
                self.upload_directory(source_path_tmp, target_path_tmp, torrent)

    def upload_file(self, source_path, target_path, torrent):
        try:
            if self.source_type == "local":
                logger.debug(f"Uploading {source_path} to {self.sftp_client.host}:{target_path}")
            else:
                logger.debug(f"Downloading {self.sftp_client.host}:{source_path} to {target_path}")
            
            if self.source_type == "local":
                file_size = os.path.getsize(source_path)
            else:
                file_size = self.sftp_client.connection.stat(source_path).st_size

            file_name = os.path.basename(source_path)
            # Set the current file name in the torrent
            torrent.current_file = file_name
            torrent.progress = 0
            torrent.transfer_speed = 0
            torrent.current_file_count += 1

            # Add variables to track transfer speed
            last_sent = 0
            last_time = time.time()

            def progress_callback(sent, total):
                nonlocal last_sent, last_time
                current_time = time.time()
                time_diff = current_time - last_time
                
                # Only update speed if enough time has passed (avoid division by zero or rapid updates)
                if time_diff >= 0.5:  # Update speed every half second
                    bytes_diff = sent - last_sent
                    speed = bytes_diff / time_diff if time_diff > 0 else 0
                    torrent.transfer_speed = speed  # Speed in bytes per second
                    
                    # Update last values for next calculation
                    last_sent = sent
                    last_time = current_time
                
                torrent.progress = sent / file_size * 100

            if self.source_type == "local":
                logger.debug(f"Uploading {source_path} to {self.sftp_client.host}:{target_path}")
                self.sftp_client.connection.put(source_path, target_path, callback=progress_callback)
            else:
                logger.debug(f"Downloading {self.sftp_client.host}:{source_path} to {target_path}")
                self.sftp_client.connection.get(source_path, target_path, callback=progress_callback)

            torrent.progress = 100  # Mark progress as complete
            torrent.transfer_speed = 0  # Reset speed when complete
            return True
        except Exception as e:
            logger.error(f"FTP upload failed: {e}")
            traceback.print_exc()
            torrent.progress = 0  # Reset progress on failure
            torrent.transfer_speed = 0  # Reset speed on failure
            return False
        
    def file_exists_on_source(self, path):
        if self.source_type == "local":
            return os.path.isfile(path)
        else:
            try:
                self.sftp_client.open_connection()
                return self.sftp_client.connection.isfile(path)
            except Exception as e:
                logger.error(f"Error checking file existence on source: {e}")
                return False
            finally:
                self.sftp_client.close()


class SFTPAndSFTPClient(TransferClient):

    def __init__(self, source_sftp_config, target_sftp_config):
        self._init_sftp_clients(source_sftp_config, target_sftp_config)
        self.current_progress = {}


    def _init_sftp_clients(self, source_sftp_config, target_sftp_config):
        try:
            self.source_sftp_client = SFTPClient(**source_sftp_config)
        except Exception as e:
            raise TrasnferClientException(f"Failed to initialize source SFTP client: {e}") from e
        try:
            self.target_sftp_client = SFTPClient(**target_sftp_config)
        except Exception as e:
            raise TrasnferClientException(f"Failed to initialize target SFTP client: {e}") from e

    def get_dot_torrent_file_dump(self, dot_torrent_file_path):
        self.source_sftp_client.open_connection()
        logger.debug(f"Getting .torrent file dump from {self.source_sftp_client.host}:{dot_torrent_file_path}")
        # print(self.source_sftp_client.connection.listdir("/closet-deluge/state"))
        with self.source_sftp_client.connection.open(str(dot_torrent_file_path), 'rb') as f:
            data = f.read()
            self.source_sftp_client.close()
            return b64encode(data)

    def test_connection(self):
        """Test the connection to the source and target SFTP servers"""
        try:
            self.source_sftp_client.open_connection()
            self.target_sftp_client.open_connection()
            return {"success": True, "message": "Connection successful"}
        except Exception as e:
            logger.info(f"Connection test failed: {e}")
            return {"success": False, "message": str(e)}
        finally:
            self.source_sftp_client.close()
            self.target_sftp_client.close()

    def count_files(self, source_path):
        """Count the total number of files that need to be copied"""
        return sftp_count_files(self.source_sftp_client, source_path)

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
            torrent.transfer_speed = 0
            torrent.current_file_count += 1

            # Add variables to track download speed
            last_sent_download = 0
            last_time_download = time.time()

            def download_callback(sent, total):
                nonlocal last_sent_download, last_time_download
                current_time = time.time()
                time_diff = current_time - last_time_download
                
                if time_diff >= 0.5:  # Update speed every half second
                    bytes_diff = sent - last_sent_download
                    speed = bytes_diff / time_diff if time_diff > 0 else 0
                    torrent.transfer_speed = speed  # Speed in bytes per second
                    
                    last_sent_download = sent
                    last_time_download = current_time
                
                torrent.progress = sent / file_size * 50

            logger.debug(f"Downloading {source_path} to {tmp_file_path}")
            self.source_sftp_client.connection.get(source_path, tmp_file_path, callback=download_callback)

            # Add variables to track upload speed
            last_sent_upload = 0
            last_time_upload = time.time()

            def upload_callback(sent, total):
                nonlocal last_sent_upload, last_time_upload
                current_time = time.time()
                time_diff = current_time - last_time_upload
                
                if time_diff >= 0.5:  # Update speed every half second
                    bytes_diff = sent - last_sent_upload
                    speed = bytes_diff / time_diff if time_diff > 0 else 0
                    torrent.transfer_speed = speed  # Speed in bytes per second
                    
                    last_sent_upload = sent
                    last_time_upload = current_time
                
                torrent.progress = 50 + (sent / file_size * 50)  # Second half of progress

            logger.debug(f"Uploading {tmp_file_path} to {target_path}")
            self.target_sftp_client.connection.put(tmp_file_path, target_path, callback=upload_callback)

            os.remove(tmp_file_path)
            torrent.progress = 100  # Mark progress as complete
            torrent.transfer_speed = 0  # Reset speed when complete
            return True
        except Exception as e:
            logger.error(f"FTP upload failed: {e}")
            traceback.print_exc()
            torrent.progress = 0  # Reset progress on failure
            torrent.transfer_speed = 0  # Reset speed on failure
            return False
        
    def file_exists_on_source(self, path):
        try:
            self.source_sftp_client.open_connection()
            return self.source_sftp_client.connection.isfile(path)
        except Exception as e:
            logger.error(f"Error checking file existence on source: {e}")
            return False
        finally:
            self.source_sftp_client.close()

def sftp_count_files(sftp_client, original_path):
    """Count the total number of files that need to be copied"""
    try:
        file_count = 0
        
        def count_recursively(path):
            nonlocal file_count
            if sftp_client.connection.isfile(path):
                file_count += 1
            elif sftp_client.connection.isdir(path):
                for item in sftp_client.connection.listdir(path):
                    count_recursively(os.path.join(path, item))
        
        count_recursively(original_path)
        return file_count
    except Exception as e:
        logger.error(f"Error counting files: {e}")
        return 0
    
def local_count_files(original_path):
    try:
        file_count = 0
        
        def count_recursively(path):
            nonlocal file_count
            if os.path.isfile(path):
                file_count += 1
            elif os.path.isdir(path):
                for item in os.listdir(path):
                    count_recursively(os.path.join(path, item))
        
        count_recursively(original_path)
        return file_count
    except Exception as e:
        logger.error(f"Error counting files: {e}")
        return 0

def get_transfer_client(from_config,to_config):
    from_connection_type = from_config.get('type')
    to_connection_type = to_config.get('type')
    if from_connection_type == 'sftp':
        if to_connection_type == 'sftp':
            return SFTPAndSFTPClient(from_config["sftp"], to_config["sftp"])
        elif to_connection_type == 'local':
            return LocalAndSFTPClient(from_config["sftp"], source_type="sftp")
        else:
            logger.error(f"Invalid connection type for target client: {to_connection_type}")
            return None
    elif from_connection_type == 'local':
        if to_connection_type == 'sftp':
            return LocalAndSFTPClient(to_config["sftp"], source_type="local")
        # elif to_connection_type == 'local':
        #     return LocalStorageClient()
        else:
            logger.error(f"Invalid connection type for target client: {to_connection_type}")
            return None
    else:
        logger.error(f"Invalid connection type for from client: {from_connection_type}")
        return None


