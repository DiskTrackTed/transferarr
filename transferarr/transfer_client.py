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

    def get_dot_torrent_file_dump(self, dot_torrent_file_path):
        self.source_sftp_client.open_connection()
        logger.debug(f"Getting .torrent file dump from {self.source_sftp_client.host}:{dot_torrent_file_path}")
        # print(self.source_sftp_client.connection.listdir("/closet-deluge/state"))
        with self.source_sftp_client.connection.open(str(dot_torrent_file_path), 'rb') as f:
            data = f.read()
            self.source_sftp_client.close()
            return b64encode(data)

    def upload(self, source_path, target_path):
        logger.debug(f"Uploading {self.source_sftp_client.host}:{source_path} to {self.target_sftp_client.host}:{target_path}")
        try:
            self.source_sftp_client.open_connection()
            self.target_sftp_client.open_connection()
            target_path = os.path.join(target_path, os.path.basename(source_path))
            if self.source_sftp_client.connection.isfile(source_path):
                self.upload_file(source_path, target_path)
            else:
                self.upload_directory(source_path, target_path)
            return True
        except Exception as e:
            logger.error(f"FTP upload failed: {e}")
            traceback.print_exc()
            return False
        finally:
            self.source_sftp_client.close()
            self.target_sftp_client.close()
    
    def upload_directory(self, source_path, target_path):
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
                self.upload_file(source_path_tmp, target_path_tmp)
            elif self.source_sftp_client.connection.isdir(source_path_tmp):
                self.upload_directory(source_path_tmp, target_path_tmp)

    def upload_file(self, source_path, target_path, chunk_size=4*1024*1024):
        try:
            ### Need to copy source to local tmp, then upload to target
            logger.debug(f"Uploading {self.source_sftp_client.host}:{source_path} to {self.target_sftp_client.host}:{target_path}")
            random_id = str(uuid.uuid4())
            tmp_file_path = os.path.join("/tmp", f"transferarr-{random_id}.tmp")
            file_size = self.source_sftp_client.connection.stat(source_path).st_size
            logger.debug(f"Downloading {source_path} to {tmp_file_path}")
            with tqdm(total=file_size, unit='B', unit_scale=True, 
                    desc=f"Get: {os.path.basename(source_path)}") as pbar:
                self.source_sftp_client.connection.get(source_path, tmp_file_path,
                                        callback=lambda sent, total: pbar.update(sent - pbar.n))
            logger.debug(f"Uploading {tmp_file_path} to {target_path}")
            with tqdm(total=file_size, unit='B', unit_scale=True, 
                    desc=f"Put: {os.path.basename(source_path)}") as pbar:
                self.target_sftp_client.connection.put(tmp_file_path, target_path, 
                                callback=lambda sent, total: pbar.update(sent - pbar.n))
            os.remove(tmp_file_path)
            return True
        except Exception as e:
            logger.error(f"FTP upload failed: {e}")
            traceback.print_exc()
            return False

        # try:
        #     logger.debug(f"Uploading {self.source_sftp_client.host}:{source_path} to {self.target_sftp_client.host}:{target_path}")
        #     # Check if target file exists and get its size
        #     try:
        #         existing_size = self.target_sftp_client.connection.stat(target_path).st_size
        #     except Exception:
        #         existing_size = 0
            
        #     file_size = self.source_sftp_client.connection.stat(source_path).st_size
            
        #     if existing_size == file_size:
        #         logger.info("File already fully transferred")
        #         return True
            
        #     logger.info(f"Resuming transfer at {existing_size}/{file_size} bytes")
            
        #     with tqdm(total=file_size, unit='B', unit_scale=True, 
        #                 unit_divisor=1024, initial=existing_size, mininterval=0.5,
        #                 desc=f"Transferring {os.path.basename(source_path)}") as pbar:
        #         with self.source_sftp_client.connection.open(source_path, 'rb', bufsize=chunk_size) as src_file, \
        #             self.target_sftp_client.connection.open(target_path, 'ab' if existing_size else 'wb', bufsize=chunk_size) as dst_file:
                    
        #             if existing_size:
        #                 src_file.seek(existing_size)
                    
        #             while True:
        #                 start = time.time_ns()
        #                 chunk = src_file.read(chunk_size)
        #                 duration = (time.time_ns() - start) / 1e9
        #                 logger.debug(f"Read {len(chunk)} bytes in {duration:.2f} seconds")
        #                 if not chunk:
        #                     break
        #                 start = time.time_ns()
        #                 dst_file.write(chunk)
        #                 duration = (time.time_ns() - start) / 1e9
        #                 logger.debug(f"Wrote {len(chunk)} bytes in {duration:.2f} seconds")
        #                 # logger.debug(f"Transferred up to {src_file.tell()}/{file_size} bytes")
        #                 pbar.update(len(chunk))
                
        #         logger.info("Transfer completed")
        #         return True
            
        # except Exception as e:
        #     logger.error(f"Transfer failed: {str(e)}")
        #     traceback.print_exc()
        #     return False
    

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


