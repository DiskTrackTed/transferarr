import os
import logging
import traceback
import stat
from tqdm import tqdm
from paramiko import SSHConfig
import pysftp

logger = logging.getLogger(__name__)

class SFTPClient():
    def __init__(self, host=None, port=22, username=None, password=None, private_key=None, ssh_config_host=None, ssh_config_file='~/.ssh/config'):
        """
        Connect using either:
        - Direct credentials (host, username, password/key)
        - SSH config host alias
        """
        cnopts = pysftp.CnOpts()
        cnopts.hostkeys = None

        self.host = host
        self.port = port
        
        if ssh_config_host:
            logger.debug(f"Setup SFTP using ssh config {ssh_config_file} and host: {ssh_config_host}")
            config = SSHConfig()
            with open(os.path.expanduser(ssh_config_file)) as f:
                config.parse(f)
            host_config = config.lookup(ssh_config_host)
            self.host = host_config.get('hostname', ssh_config_host)
            self.port = host_config.get('port', port)
            self.connection_args = {
                'host': self.host,
                'port': self.port,
                'username': host_config.get('user', username),
                'private_key': host_config.get('identityfile', private_key)[0],
                'cnopts': cnopts
            }
        else:
            logger.debug(f"Attempting SFTP using direct credentials: {host}:{port} {username}")
            self.connection_args = {
                'host': host,
                'port': port,
                'username': username,
                'password': password,
                'cnopts': cnopts
            }
        self.open_connection()
        self.connection.close()

    def stat(self, path):
        self.open_connection()
        self.connection.stat(path)
        self.close()

    def open_connection(self):
        self.connection = pysftp.Connection(**self.connection_args)
    
    def upload_file(self, local_path, remote_path):
        """Upload single file with progress bar"""
        logger.info(f"Uploading {local_path} to {self.host}:{remote_path}")
        file_size = os.path.getsize(local_path)
        with tqdm(total=file_size, unit='B', unit_scale=True, 
                 desc=os.path.basename(local_path)) as pbar:
            self.connection.put(local_path, remote_path, 
                              callback=lambda sent, total: pbar.update(sent - pbar.n))
    
    def upload_directory(self, local_dir, remote_dir):
        """Recursively upload directory with progress"""
        try:
            self.connection.makedirs(remote_dir)
        except OSError:
            pass  # Directory exists

        
        for item in os.listdir(local_dir):
            local_path = os.path.join(local_dir, item)
            remote_path = os.path.join(remote_dir, item)
            
            if os.path.isfile(local_path):
                self.upload_file(local_path, remote_path)
            elif os.path.isdir(local_path):
                self.upload_directory(local_path, remote_path)


    def upload(self, local_path, target_path):
        """Upload file or directory using FTP"""
        logger.debug(f"Uploading {local_path} to {self.host}:{target_path}")
        try:
            self.open_connection()
            target_path = os.path.join(target_path, os.path.basename(local_path))
            if os.path.isfile(local_path):
                self.upload_file(local_path, target_path)
            else:
                self.upload_directory(local_path, target_path)
            return True
        except Exception as e:
            logger.error(f"FTP upload failed: {e}")
            traceback.print_exc()
            return False
        finally:
            self.connection.close()

    def close(self):
        try:
            self.connection.close()
        except Exception as e:
            logger.error(f"Failed to close SFTP connection: {e}")

    def normalize(self,path):
        """Normalize path for SFTP"""
        self.open_connection()
        new_path = self.connection.normalize(path)
        self.close()
        return new_path
    
    def list_dir(self, path):
        """List directory contents"""
        try:
            self.open_connection()
            entries_with_stat = []
            for attr in self.connection.listdir_attr(path):
                name = attr.filename
                full_path = os.path.join(path, name)
                is_dir = stat.S_ISDIR(attr.st_mode)
                entry = {
                    "name": name,
                    "path": full_path,
                    "is_dir": is_dir
                    # "size": size
                }
                entries_with_stat.append(entry)
            self.close()
            return entries_with_stat
        except Exception as e:
            raise e
        finally:
            self.close()