"""Private BitTorrent tracker for torrent-based transfers.

Implements a lightweight HTTP tracker (BEP 3) for peer discovery during
torrent-based transfers. Only tracks transfer torrents registered by Transferarr.
"""

import logging
import socket
import struct
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
from urllib.parse import parse_qs, urlparse, unquote_to_bytes
import re

logger = logging.getLogger("transferarr")


def bencode(data) -> bytes:
    """Encode data to bencode format.
    
    Args:
        data: Python object to encode (dict, list, int, str, bytes)
        
    Returns:
        Bencoded bytes
    """
    if isinstance(data, int):
        return f"i{data}e".encode()
    elif isinstance(data, bytes):
        return f"{len(data)}:".encode() + data
    elif isinstance(data, str):
        encoded = data.encode()
        return f"{len(encoded)}:".encode() + encoded
    elif isinstance(data, list):
        return b"l" + b"".join(bencode(item) for item in data) + b"e"
    elif isinstance(data, dict):
        result = b"d"
        for key in sorted(data.keys()):
            result += bencode(key) + bencode(data[key])
        result += b"e"
        return result
    else:
        raise TypeError(f"Cannot bencode type: {type(data)}")


def encode_compact_peers(peers: list[tuple[str, int]]) -> bytes:
    """Encode peer list to compact format (BEP 23).
    
    Args:
        peers: List of (ip_address, port) tuples
        
    Returns:
        Compact peer bytes (6 bytes per peer: 4 IP + 2 port)
    """
    result = b""
    for ip, port in peers:
        try:
            ip_bytes = socket.inet_aton(ip)
            port_bytes = struct.pack(">H", port)
            result += ip_bytes + port_bytes
        except (socket.error, struct.error) as e:
            logger.warning(f"Failed to encode peer {ip}:{port}: {e}")
    return result


class TrackerState:
    """Thread-safe state for the tracker.
    
    Stores registered transfer hashes (whitelist) and peer information.
    """
    
    DEFAULT_PEER_EXPIRY = 120  # seconds
    
    def __init__(self, peer_expiry: int = DEFAULT_PEER_EXPIRY):
        """Initialize tracker state.
        
        Args:
            peer_expiry: Seconds after which a peer is considered expired
        """
        self._lock = threading.Lock()
        self._whitelist: set[bytes] = set()  # Registered info_hashes
        self._peers: dict[bytes, dict[bytes, dict]] = {}  # info_hash -> peer_id -> peer_info
        self.peer_expiry = peer_expiry
    
    def register_transfer(self, info_hash: bytes) -> None:
        """Register a transfer hash (add to whitelist).
        
        Args:
            info_hash: 20-byte info_hash of the transfer torrent
        """
        with self._lock:
            self._whitelist.add(info_hash)
            if info_hash not in self._peers:
                self._peers[info_hash] = {}
            logger.debug(f"Registered transfer hash: {info_hash.hex()}")
    
    def unregister_transfer(self, info_hash: bytes) -> None:
        """Unregister a transfer hash (remove from whitelist).
        
        Args:
            info_hash: 20-byte info_hash of the transfer torrent
        """
        with self._lock:
            self._whitelist.discard(info_hash)
            self._peers.pop(info_hash, None)
            logger.debug(f"Unregistered transfer hash: {info_hash.hex()}")
    
    def is_registered(self, info_hash: bytes) -> bool:
        """Check if an info_hash is registered (whitelisted).
        
        Args:
            info_hash: 20-byte info_hash to check
            
        Returns:
            True if registered, False otherwise
        """
        with self._lock:
            return info_hash in self._whitelist
    
    def get_registered_count(self) -> int:
        """Get the number of registered transfer hashes.
        
        Returns:
            Number of hashes in the whitelist
        """
        with self._lock:
            return len(self._whitelist)
    
    def get_scrape_stats(self, info_hash: bytes) -> dict:
        """Get scrape statistics for a registered info_hash.
        
        Thread-safe method that counts seeders (left=0) and leechers (left>0).
        
        Args:
            info_hash: 20-byte info_hash to get stats for
            
        Returns:
            Dict with 'complete' (seeders) and 'incomplete' (leechers) counts
        """
        with self._lock:
            peer_data = self._peers.get(info_hash, {})
            complete = 0
            incomplete = 0
            for pinfo in peer_data.values():
                if pinfo.get("left", 0) == 0:
                    complete += 1
                else:
                    incomplete += 1
            return {"complete": complete, "incomplete": incomplete}
    
    def update_peer(
        self,
        info_hash: bytes,
        peer_id: bytes,
        ip: str,
        port: int,
        left: int
    ) -> None:
        """Update peer information for a torrent.
        
        Args:
            info_hash: 20-byte info_hash
            peer_id: 20-byte peer_id
            ip: Peer IP address
            port: Peer port number
            left: Bytes left to download (0 = seeder)
        """
        with self._lock:
            if info_hash not in self._peers:
                self._peers[info_hash] = {}
            
            self._peers[info_hash][peer_id] = {
                "ip": ip,
                "port": port,
                "left": left,
                "last_seen": time.time()
            }
            logger.debug(f"Updated peer {peer_id.hex()[:8]} for {info_hash.hex()[:8]}: {ip}:{port}")
    
    def remove_peer(self, info_hash: bytes, peer_id: bytes) -> None:
        """Remove a peer from tracking.
        
        Args:
            info_hash: 20-byte info_hash
            peer_id: 20-byte peer_id
        """
        with self._lock:
            if info_hash in self._peers:
                self._peers[info_hash].pop(peer_id, None)
    
    def get_peers(self, info_hash: bytes, exclude_peer_id: Optional[bytes] = None) -> list[tuple[str, int]]:
        """Get list of peers for a torrent.
        
        Args:
            info_hash: 20-byte info_hash
            exclude_peer_id: Optional peer_id to exclude from results
            
        Returns:
            List of (ip, port) tuples for active peers
        """
        now = time.time()
        result = []
        
        with self._lock:
            if info_hash not in self._peers:
                return []
            
            for peer_id, info in list(self._peers[info_hash].items()):
                # Skip expired peers
                if now - info["last_seen"] > self.peer_expiry:
                    del self._peers[info_hash][peer_id]
                    continue
                
                # Skip the requesting peer
                if exclude_peer_id and peer_id == exclude_peer_id:
                    continue
                
                result.append((info["ip"], info["port"]))
        
        return result
    
    def cleanup_expired_peers(self) -> int:
        """Remove all expired peers.
        
        Returns:
            Number of peers removed
        """
        now = time.time()
        removed = 0
        
        with self._lock:
            for info_hash in list(self._peers.keys()):
                for peer_id, info in list(self._peers[info_hash].items()):
                    if now - info["last_seen"] > self.peer_expiry:
                        del self._peers[info_hash][peer_id]
                        removed += 1
        
        return removed


class AnnounceRequest:
    """Parsed announce request parameters."""
    
    def __init__(
        self,
        info_hash: bytes,
        peer_id: bytes,
        port: int,
        uploaded: int,
        downloaded: int,
        left: int,
        event: str,
        compact: bool,
        ip: Optional[str] = None
    ):
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.port = port
        self.uploaded = uploaded
        self.downloaded = downloaded
        self.left = left
        self.event = event
        self.compact = compact
        self.ip = ip
    
    @classmethod
    def from_query_string(cls, query_string: str, client_ip: str) -> "AnnounceRequest":
        """Parse announce request from query string.
        
        Args:
            query_string: URL query string
            client_ip: Client's IP address from connection
            
        Returns:
            AnnounceRequest instance
            
        Raises:
            ValueError: If required parameters are missing or invalid
        """
        params = parse_qs(query_string, keep_blank_values=True)
        
        # Required parameters
        if "info_hash" not in params:
            raise ValueError("Missing required parameter: info_hash")
        if "peer_id" not in params:
            raise ValueError("Missing required parameter: peer_id")
        if "port" not in params:
            raise ValueError("Missing required parameter: port")
        
        # info_hash and peer_id are URL-encoded binary data.
        # parse_qs decodes them as UTF-8 strings which corrupts binary data.
        # We need to extract them from the raw query string and use unquote_to_bytes.
        def extract_binary_param(query: str, param_name: str) -> bytes:
            """Extract URL-encoded binary parameter directly from query string."""
            # Match param_name=value (value ends at & or end of string)
            pattern = rf'{param_name}=([^&]*)'
            match = re.search(pattern, query)
            if not match:
                raise ValueError(f"Missing required parameter: {param_name}")
            return unquote_to_bytes(match.group(1))
        
        info_hash = extract_binary_param(query_string, "info_hash")
        if len(info_hash) != 20:
            raise ValueError(f"Invalid info_hash length: {len(info_hash)} (expected 20)")
        
        peer_id = extract_binary_param(query_string, "peer_id")
        if len(peer_id) != 20:
            raise ValueError(f"Invalid peer_id length: {len(peer_id)} (expected 20)")
        
        try:
            port = int(params["port"][0])
        except (ValueError, IndexError):
            raise ValueError("Invalid port")
        
        # Optional parameters with defaults
        uploaded = int(params.get("uploaded", [0])[0])
        downloaded = int(params.get("downloaded", [0])[0])
        left = int(params.get("left", [0])[0])
        event = params.get("event", [""])[0]
        compact = params.get("compact", ["1"])[0] == "1"
        
        # IP: prefer explicit ip param, fall back to client connection IP
        ip = params.get("ip", [client_ip])[0]
        
        return cls(
            info_hash=info_hash,
            peer_id=peer_id,
            port=port,
            uploaded=uploaded,
            downloaded=downloaded,
            left=left,
            event=event,
            compact=compact,
            ip=ip
        )


class TrackerRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for tracker announce requests.
    
    NOTE: tracker_state and announce_interval are shared via class variables
    because Python's HTTPServer creates a new handler instance per request,
    with no built-in way to pass state to the constructor. BitTorrentTracker.start()
    sets these before the server begins accepting requests. This is safe as long as
    only one BitTorrentTracker instance runs at a time (enforced by the application).
    """
    
    # Set by BitTorrentTracker.start() before server begins accepting requests
    tracker_state: TrackerState = None
    announce_interval: int = 60
    
    def log_message(self, format, *args):
        """Override to use our logger."""
        logger.debug(f"Tracker: {args[0]}")
    
    def do_GET(self):
        """Handle GET requests (announce and scrape)."""
        parsed = urlparse(self.path)
        
        if parsed.path == "/announce":
            self._handle_announce(parsed.query)
        elif parsed.path == "/scrape":
            self._handle_scrape(parsed.query)
        else:
            self.send_error(404, "Not Found")
    
    def _handle_announce(self, query_string: str):
        """Handle announce request.
        
        Args:
            query_string: URL query string
        """
        try:
            # Parse request
            client_ip = self.client_address[0]
            request = AnnounceRequest.from_query_string(query_string, client_ip)
            
            # Check whitelist
            if not self.tracker_state.is_registered(request.info_hash):
                logger.debug(f"Announce for unregistered hash: {request.info_hash.hex()}")
                # Return empty peers for unregistered hashes
                response = self._build_response([], request.compact)
                self._send_response(response)
                return
            
            # Handle event
            if request.event == "stopped":
                self.tracker_state.remove_peer(request.info_hash, request.peer_id)
            else:
                # Update peer (started, completed, or regular announce)
                self.tracker_state.update_peer(
                    request.info_hash,
                    request.peer_id,
                    request.ip,
                    request.port,
                    request.left
                )
            
            # Get peers (excluding the requesting peer)
            peers = self.tracker_state.get_peers(request.info_hash, request.peer_id)
            
            # Build and send response
            response = self._build_response(peers, request.compact)
            self._send_response(response)
            
        except ValueError as e:
            logger.warning(f"Invalid announce request: {e}")
            error_response = bencode({"failure reason": str(e)})
            self._send_response(error_response)
    
    def _handle_scrape(self, query_string: str):
        """Handle scrape request.
        
        Returns peer statistics for requested info_hashes.
        Implements BEP 48 (scrape convention).
        
        Args:
            query_string: URL query string with info_hash parameter(s)
        """
        try:
            # Extract all info_hash parameters from query string
            files = {}
            
            # Find all info_hash values in query string
            for match in re.finditer(r'info_hash=([^&]*)', query_string):
                try:
                    info_hash = unquote_to_bytes(match.group(1))
                    if len(info_hash) != 20:
                        continue
                    
                    if self.tracker_state.is_registered(info_hash):
                        stats = self.tracker_state.get_scrape_stats(info_hash)
                        files[info_hash] = {
                            "complete": stats["complete"],
                            "downloaded": 0,
                            "incomplete": stats["incomplete"]
                        }
                    else:
                        # Return zeros for unregistered hashes
                        files[info_hash] = {
                            "complete": 0,
                            "downloaded": 0,
                            "incomplete": 0
                        }
                except Exception:
                    continue
            
            response = bencode({"files": files})
            self._send_response(response)
            
        except Exception as e:
            logger.warning(f"Invalid scrape request: {e}")
            error_response = bencode({"failure reason": str(e)})
            self._send_response(error_response)
    
    def _build_response(self, peers: list[tuple[str, int]], compact: bool) -> bytes:
        """Build announce response.
        
        Args:
            peers: List of (ip, port) tuples
            compact: Whether to use compact peer format
            
        Returns:
            Bencoded response
        """
        if compact:
            peer_data = encode_compact_peers(peers)
        else:
            # Non-compact format (dict per peer)
            peer_data = [
                {"ip": ip, "port": port}
                for ip, port in peers
            ]
        
        return bencode({
            "interval": self.announce_interval,
            "peers": peer_data
        })
    
    def _send_response(self, data: bytes):
        """Send bencoded response.
        
        Args:
            data: Bencoded response data
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)


class BitTorrentTracker:
    """Private BitTorrent tracker for torrent-based transfers.
    
    Runs an HTTP server implementing the BitTorrent tracker protocol (BEP 3).
    Only tracks transfer torrents explicitly registered by Transferarr.
    """
    
    DEFAULT_PORT = 6969
    DEFAULT_ANNOUNCE_INTERVAL = 60
    DEFAULT_PEER_EXPIRY = 120
    
    def __init__(
        self,
        port: int = DEFAULT_PORT,
        external_url: Optional[str] = None,
        announce_interval: int = DEFAULT_ANNOUNCE_INTERVAL,
        peer_expiry: int = DEFAULT_PEER_EXPIRY
    ):
        """Initialize the tracker.
        
        Args:
            port: Port to listen on
            external_url: URL clients use to reach tracker (for magnet URIs)
            announce_interval: Seconds between client announces
            peer_expiry: Seconds after which peers are considered expired
        """
        self.port = port
        self.external_url = external_url or f"http://localhost:{port}/announce"
        self.announce_interval = announce_interval
        self.state = TrackerState(peer_expiry=peer_expiry)
        
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
    
    @property
    def is_running(self) -> bool:
        """Whether the tracker is currently running."""
        return self._running
    
    def start(self) -> None:
        """Start the tracker server in a background thread."""
        if self._running:
            logger.warning("Tracker already running")
            return
        
        # Set class-level state on the handler before the server starts.
        # See TrackerRequestHandler docstring for why class variables are used.
        TrackerRequestHandler.tracker_state = self.state
        TrackerRequestHandler.announce_interval = self.announce_interval
        
        try:
            self._server = HTTPServer(("0.0.0.0", self.port), TrackerRequestHandler)
        except OSError as e:
            raise RuntimeError(f"Failed to start tracker on port {self.port}: {e}")
        
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        
        logger.info(f"BitTorrent tracker started on port {self.port}")
        logger.info(f"Tracker external URL: {self.external_url}")
    
    def stop(self) -> None:
        """Stop the tracker server."""
        if not self._running:
            return
        
        self._running = False
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        
        logger.info("BitTorrent tracker stopped")
    
    def _serve(self) -> None:
        """Server loop (runs in background thread).
        
        Uses serve_forever() which cooperates with shutdown() for clean stopping.
        """
        self._server.serve_forever()
    
    def register_transfer(self, info_hash: bytes) -> None:
        """Register a transfer torrent hash (add to whitelist).
        
        Args:
            info_hash: 20-byte info_hash of the transfer torrent
        """
        self.state.register_transfer(info_hash)
    
    def unregister_transfer(self, info_hash: bytes) -> None:
        """Unregister a transfer torrent hash (remove from whitelist).
        
        Args:
            info_hash: 20-byte info_hash of the transfer torrent
        """
        self.state.unregister_transfer(info_hash)
    
    def is_registered(self, info_hash: bytes) -> bool:
        """Check if a hash is registered.
        
        Args:
            info_hash: 20-byte info_hash to check
            
        Returns:
            True if registered
        """
        return self.state.is_registered(info_hash)
    
    def get_peers(self, info_hash: bytes) -> list[tuple[str, int]]:
        """Get peers for a torrent (for testing/debugging).
        
        Args:
            info_hash: 20-byte info_hash
            
        Returns:
            List of (ip, port) tuples
        """
        return self.state.get_peers(info_hash)
    
    def get_status(self) -> dict:
        """Get tracker status information.
        
        Returns:
            Dict with enabled, running, port, and active_transfers count
        """
        return {
            "enabled": True,
            "running": self.is_running,
            "port": self.port,
            "active_transfers": self.state.get_registered_count()
        }


def get_tracker_config(config: dict) -> dict:
    """Get tracker configuration with defaults.
    
    Args:
        config: Application configuration dict
        
    Returns:
        Tracker config dict with defaults applied
    """
    tracker_config = config.get("tracker", {})
    return {
        "enabled": tracker_config.get("enabled", True),
        "port": tracker_config.get("port", BitTorrentTracker.DEFAULT_PORT),
        "external_url": tracker_config.get("external_url"),
        "announce_interval": tracker_config.get("announce_interval", BitTorrentTracker.DEFAULT_ANNOUNCE_INTERVAL),
        "peer_expiry": tracker_config.get("peer_expiry", BitTorrentTracker.DEFAULT_PEER_EXPIRY)
    }


def create_tracker_from_config(config: dict) -> Optional[BitTorrentTracker]:
    """Create a BitTorrentTracker from configuration.
    
    Args:
        config: Application configuration dict
        
    Returns:
        BitTorrentTracker instance or None if disabled
    """
    tracker_config = get_tracker_config(config)
    
    if not tracker_config["enabled"]:
        return None
    
    return BitTorrentTracker(
        port=tracker_config["port"],
        external_url=tracker_config["external_url"],
        announce_interval=tracker_config["announce_interval"],
        peer_expiry=tracker_config["peer_expiry"]
    )
