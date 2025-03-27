from ftplib import FTP, error_perm
import os
import logging
from tqdm import tqdm
from paramiko import SSHConfig
import pysftp

logger = logging.getLogger(__name__)

class SFTPClientWithProgress:
    def __init__(self, host=None, username=None, password=None, private_key=None, ssh_config_host=None):
        """
        Connect using either:
        - Direct credentials (host, username, password/key)
        - SSH config host alias
        """
        cnopts = pysftp.CnOpts()
        cnopts.hostkeys = None 
        
        if ssh_config_host:
            logger.debug(f"SFTP using ssh config host: {ssh_config_host}")
            config = SSHConfig()
            with open(os.path.expanduser("~/.ssh/config")) as f:
                config.parse(f)
            host_config = config.lookup(ssh_config_host)
            self.host = host_config.get('hostname', ssh_config_host)
            self.connection = pysftp.Connection(
                host=self.host,
                username=host_config.get('user', username),
                private_key=host_config.get('identityfile', private_key)[0],
                cnopts=cnopts
            )
        else:
            self.connection = pysftp.Connection(
                host=host,
                username=username,
                password=password,
                private_key=private_key,
                cnopts=cnopts
            )
    
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
    
    def close(self):
        self.connection.close()


def ftp_upload(local_path, remote_path, host):
    """Upload file or directory using FTP with progress bar"""
    logger.debug(f"Uploading {local_path} to {host}:{remote_path}")
    sftp = SFTPClientWithProgress(ssh_config_host=host)  # or direct credentials
    try:
        if os.path.isfile(local_path):
            sftp.upload_file(local_path, remote_path)
        else:
            remote_path = os.path.join(remote_path, os.path.basename(local_path))
            sftp.upload_directory(local_path, remote_path)
        return True
    except Exception as e:
        logger.error(f"FTP upload failed: {e}")
        return False
    finally:
        sftp.close()