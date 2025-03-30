import os
import subprocess
import shlex
import logging
from base64 import b64encode
from pathlib import Path
from transferarr.torrent import TorrentState

logger = logging.getLogger(__name__)

def transfer_file_scp_cli(source, server, destination):
    """Transfer file using system SCP command with SSH config"""
    cmd = ['scp']
    if Path(source).is_dir():
        cmd = cmd + ['-r']
    cmd = cmd + [source, f'{server}:{destination}']
    try:
        logger.info(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
        logger.info("File transferred successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"SCP transfer failed: {e}")

def decode_bytes(obj):
    if isinstance(obj, dict):
        return {decode_bytes(key): decode_bytes(value) 
                for key, value in obj.items()}
    if isinstance(obj, list):
        return [decode_bytes(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(decode_bytes(item) for item in obj)
    if isinstance(obj, bytes):
        return obj.decode('utf-8')
    return obj

def get_paths_to_copy(torrent):
    paths = set()
    files = torrent.home_client_info['files']
    for file in files:
        paths.add(file['path'].split(os.sep)[0])
    return paths