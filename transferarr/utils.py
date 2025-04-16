import os
import subprocess
import logging
import time
from pathlib import Path
from flask import jsonify
from transferarr.clients.ftp import SFTPClient

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

def connection_modal_browse(path, connection_type, connection_config):
    try:
        if connection_type == "local":
            return browse_local(path)
        
        elif connection_type == "sftp":
            if "sftp" not in connection_config:
                return jsonify({
                    "error": "SFTP configuration not provided",
                    "entries": [],
                    "current_path": path
                }), 400
            sftp_config = connection_config["sftp"]
            return browse_sftp(path, sftp_config)
        else:
            return jsonify({
                "error": f"Unsupported connection type: {connection_type}",
                "entries": [],
                "current_path": path
            }), 400
            
    except Exception as e:
        logger.error(f"Error in browse_directory: {e}")
        return jsonify({
            "error": f"Server error: {str(e)}",
            "entries": []
        }), 500


def browse_local(path):
    try:
        expanded_path = os.path.expanduser(path)
        
        # Check if path exists
        if not os.path.exists(expanded_path):
            return jsonify({
                "error": f"Path does not exist: {path}",
                "entries": [],
                "current_path": path
            }), 404
        
        # Check if it's a directory
        if not os.path.isdir(expanded_path):
            return jsonify({
                "error": f"Path is not a directory: {path}",
                "entries": [],
                "current_path": path
            }), 400
        
        # List directory contents
        entries = []
        for entry in os.listdir(expanded_path):
            entry_path = os.path.join(expanded_path, entry)
            entries.append({
                "name": entry,
                "path": entry_path,
                "is_dir": os.path.isdir(entry_path)
                # "size": os.path.getsize(entry_path) if os.path.isfile(entry_path) else 0
            })
        
        # Sort directories first, then files
        entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        
        # Get parent directory
        parent_path = os.path.dirname(os.path.abspath(expanded_path))
        
        return jsonify({
            "entries": entries,
            "parent": parent_path,
            "current_path": expanded_path
        })
        
    except Exception as e:
        logger.error(f"Error browsing local directory {path}: {e}")
        return jsonify({
            "error": f"Error browsing directory: {str(e)}",
            "entries": [],
            "current_path": path
        }), 500
    
def browse_sftp(path, sftp_config):
    # Check if using SSH config
    try:
        start = time.time()
        sftp_client = SFTPClient(**sftp_config)
        print(f"sftp_client init took: {time.time() - start:.2f} seconds")
    except Exception as e:
        logger.error(f"Error connecting to SFTP via SSH config: {e}")
        return jsonify({
            "error": f"Error connecting to SFTP: {str(e)}",
            "entries": [],
            "current_path": path
        }), 500
    
    try:
        
        # Expand path (handle ~ for home directory)
        if path.startswith("~"):
            path = sftp_client.normalize(path)
            if path.endswith("~"):
                path = path[:-1]
        
        # List directory contents
        entries = sftp_client.list_dir(path)
        
        # Sort directories first, then files
        entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        
        # Get parent directory
        parent_path = os.path.dirname(os.path.normpath(path))
        if parent_path == "":
            parent_path = "/"
        
        return jsonify({
            "entries": entries,
            "parent": parent_path,
            "current_path": path
        })
        
    except Exception as e:
        logger.error(f"Error browsing SFTP directory {path}: {e}")
        
        return jsonify({
            "error": f"Error browsing directory: {str(e)}",
            "entries": [],
            "current_path": path
        }), 500