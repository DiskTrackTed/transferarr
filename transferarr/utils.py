import os
import subprocess
import logging
import time
import secrets
import string
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, parse_qs
from flask import jsonify

logger = logging.getLogger(__name__)

# Transfer ID generation constants
TRANSFER_ID_LENGTH = 6
TRANSFER_ID_CHARS = string.ascii_lowercase + string.digits


def generate_transfer_id() -> str:
    """Generate a unique 6-character transfer ID.
    
    Returns:
        Random alphanumeric string (e.g., 'f7e2a1')
    """
    return ''.join(secrets.choice(TRANSFER_ID_CHARS) for _ in range(TRANSFER_ID_LENGTH))


def build_transfer_torrent_name(original_name: str, transfer_id: str = None) -> str:
    """Build the transfer torrent name from original torrent name.
    
    Args:
        original_name: Original torrent name
        transfer_id: Optional transfer ID (generated if not provided)
        
    Returns:
        Transfer torrent name (e.g., '[TR-f7e2a1] Movie.2024.1080p')
    """
    if transfer_id is None:
        transfer_id = generate_transfer_id()
    return f"[TR-{transfer_id}] {original_name}"


def parse_magnet_uri(magnet_uri: str) -> dict:
    """Parse a magnet URI into its components.
    
    Args:
        magnet_uri: Magnet URI string
        
    Returns:
        Dict with keys: hash, name, trackers
        
    Raises:
        ValueError: If the URI is not a valid magnet link
    """
    if not magnet_uri.startswith("magnet:?"):
        raise ValueError("Invalid magnet URI: must start with 'magnet:?'")
    
    # Parse query string
    query = magnet_uri[8:]  # Remove 'magnet:?'
    params = parse_qs(query)
    
    result = {
        "hash": None,
        "name": None,
        "trackers": []
    }
    
    # Extract info hash from xt (exact topic)
    if "xt" in params:
        for xt in params["xt"]:
            if xt.startswith("urn:btih:"):
                result["hash"] = xt[9:].lower()  # Remove 'urn:btih:' prefix
                break
    
    # Extract display name
    if "dn" in params:
        result["name"] = unquote(params["dn"][0])
    
    # Extract trackers
    if "tr" in params:
        result["trackers"] = [unquote(tr) for tr in params["tr"]]
    
    return result


def build_magnet_uri(
    info_hash: str,
    name: str = None,
    trackers: list[str] = None
) -> str:
    """Build a magnet URI from components.
    
    Args:
        info_hash: 40-character hex info hash
        name: Optional display name
        trackers: Optional list of tracker URLs
        
    Returns:
        Magnet URI string
    """
    parts = [f"magnet:?xt=urn:btih:{info_hash.lower()}"]
    
    if name:
        parts.append(f"dn={quote(name)}")
    
    if trackers:
        for tracker in trackers:
            parts.append(f"tr={quote(tracker)}")
    
    return "&".join(parts)

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
    # Import here to avoid circular import
    from transferarr.clients.ftp import SFTPClient
    
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