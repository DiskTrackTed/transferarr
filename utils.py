import os
import subprocess
import shlex
import logging
from base64 import b64encode
from pathlib import Path
from torrent import Torrent, TorrentState
from ftp import ftp_upload

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

def scp_with_pv(local_path, server, remote_path):
    """
    Robust version that handles paths with spaces and special characters
    """
    # Properly escape all paths
    local_path_esc = shlex.quote(local_path)
    remote_path_esc = shlex.quote(remote_path)
    
    if os.path.isdir(local_path):
        # Directory transfer with proper escaping
        dir_name = os.path.basename(local_path)
        parent_dir = os.path.dirname(local_path)
        
        dir_name_esc = shlex.quote(dir_name)
        parent_dir_esc = shlex.quote(parent_dir)
        
        cmd = (
            f"tar cf - -C {parent_dir_esc} {dir_name_esc} | "
            f"pv -s $(du -sb {local_path_esc} | cut -f1) | "
            f"ssh {server} 'tar xf - -C {remote_path_esc}'"
        )
    else:
        # File transfer
        cmd = f"pv {local_path_esc} | scp - {server}:{remote_path_esc}"
    
    try:
        logger.info(f"Transferring: {local_path} → {server}:{remote_path}")
        subprocess.run(cmd, shell=True, check=True)
        logger.info("Transfer complete!")
    except subprocess.CalledProcessError as e:
        logger.error(f"Transfer failed: {e}")
    except Exception as e:
        logger.error(f"Error: {e}")

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
    files = torrent.local_deluge_info['files']
    for file in files:
        paths.add(file['path'].split(os.sep)[0])
    return paths

def ready_to_copy(torrent):
    ## not in deluge yet
    if(torrent.local_deluge_info is None):
        logger.error(f"Local deluge info is None: {torrent.name}")
        return False
    ## In deluge and seeding
    if(torrent.local_deluge_info['state'] == "Seeding"):
        ## Already seeding on SB
        if(torrent.sb_deluge_info is not None):
            logger.debug(f"Already seeding on SB: {torrent.name}")
            torrent.state = TorrentState.SB_SEEDING
            return False
        logger.debug(f"Ready to copy: {torrent.name}")
        return True
    logger.debug(f"Not seeding: {torrent.name} - {torrent.local_deluge_info['state']}")
    return False


def do_copy_files(local_client, sb_client, torrents):
    for torrent in torrents:
        if(ready_to_copy(torrent)):
            ## Copy .torrent file to tmp dir
            torrent.state = TorrentState.COPYING
            dot_torrent_file_path = str(Path(local_client.dot_torrent_path).joinpath(f"{torrent.id}.torrent"))

            if not Path(dot_torrent_file_path).exists():
                logger.error(f"Dot torrent file does not exist: {dot_torrent_file_path}")
                continue

            with open(str(dot_torrent_file_path), 'rb') as f:
                data = f.read()
                file_dump = b64encode(data)
            transfer_file_scp_cli(dot_torrent_file_path, 'sb-2', sb_client.dot_torrent_tmp_dir)
            dest_dot_torrent_path = sb_client.dot_torrent_tmp_dir + f"{id}.torrent"
            paths_to_copy = get_paths_to_copy(torrent)
            for path in paths_to_copy:
                source_file_path = str(Path(local_client.torrent_download_path).joinpath(Path(path)))
                ftp_destination = sb_client.torrent_download_path
                logger.debug(f"Copying: {source_file_path} to sb-2:{ftp_destination}")

                success = ftp_upload(source_file_path, ftp_destination, 'sb-2')
                if success == True:
                    torrent.state = TorrentState.COPIED
                else:
                    torrent.state = TorrentState.ERROR
                    break
            if torrent.state == TorrentState.COPIED:
                try:
                    sb_client.client.core.add_torrent_file(dest_dot_torrent_path, file_dump, {})
                    logger.info(f"Torrent added successfully: {torrent.name}")
                    torrent.state = TorrentState.SB_SEEDING
                except Exception as e:
                    logger.error(f"Error adding torrent: {e}")
                    torrent.state = TorrentState.ERROR


def do_torrent_cleanup(local_client, sb_client, torrents):
    for torrent in torrents:
        if(torrent.state == TorrentState.SB_SEEDING):
            logger.info(f"Removing local torrent: {torrent.name}")
            try:
                local_client.client.core.remove_torrent(torrent.id, True)
                torrents.remove(torrent)
            except Exception as e:
                logger.error(f"Error removing torrent: {e}")
                torrent.state = TorrentState.ERROR
        if(torrent.state == TorrentState.ERROR):
            logger.error(f"Error with torrent: {torrent.name}")
            continue
        if(torrent.state == TorrentState.MISSING):
            logger.warning(f"Torrent missing: {torrent.name}")