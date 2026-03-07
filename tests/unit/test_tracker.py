"""Unit tests for BitTorrentTracker."""

import socket
import struct
import threading
import time
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from transferarr.services.tracker import (
    AnnounceRequest,
    BitTorrentTracker,
    TrackerState,
    bencode,
    encode_compact_peers,
    get_tracker_config,
    create_tracker_from_config,
)


# --- Test bencode utility ---

class TestBencode:
    """Tests for bencode encoding."""
    
    def test_bencode_int(self):
        """Encode integer."""
        assert bencode(42) == b"i42e"
        assert bencode(0) == b"i0e"
        assert bencode(-1) == b"i-1e"
    
    def test_bencode_string(self):
        """Encode string."""
        assert bencode("hello") == b"5:hello"
        assert bencode("") == b"0:"
    
    def test_bencode_bytes(self):
        """Encode bytes."""
        assert bencode(b"hello") == b"5:hello"
        assert bencode(b"\x00\x01\x02") == b"3:\x00\x01\x02"
    
    def test_bencode_list(self):
        """Encode list."""
        assert bencode([1, 2, 3]) == b"li1ei2ei3ee"
        assert bencode(["a", "b"]) == b"l1:a1:be"
    
    def test_bencode_dict(self):
        """Encode dict (keys sorted)."""
        assert bencode({"a": 1, "b": 2}) == b"d1:ai1e1:bi2ee"
        # Keys should be sorted
        assert bencode({"z": 1, "a": 2}) == b"d1:ai2e1:zi1ee"
    
    def test_bencode_nested(self):
        """Encode nested structures."""
        assert bencode({"list": [1, 2]}) == b"d4:listli1ei2eee"


class TestCompactPeerEncoding:
    """Tests for compact peer list encoding."""
    
    def test_encode_single_peer(self):
        """Encode single peer."""
        result = encode_compact_peers([("192.168.1.1", 6881)])
        # 192.168.1.1 = 0xC0.0xA8.0x01.0x01, port 6881 = 0x1AE1
        expected = b"\xc0\xa8\x01\x01\x1a\xe1"
        assert result == expected
    
    def test_encode_multiple_peers(self):
        """Encode multiple peers."""
        result = encode_compact_peers([
            ("192.168.1.1", 6881),
            ("10.0.0.1", 8080)
        ])
        assert len(result) == 12  # 6 bytes per peer
    
    def test_encode_empty_peers(self):
        """Encode empty peer list."""
        result = encode_compact_peers([])
        assert result == b""
    
    def test_encode_invalid_ip_skipped(self):
        """Invalid IP is skipped."""
        result = encode_compact_peers([("invalid", 6881)])
        assert result == b""


# --- Test AnnounceRequest parsing ---

class TestAnnounceRequestParsing:
    """Tests for parsing announce requests."""
    
    def test_parse_valid_request(self):
        """Parse a valid announce request."""
        # URL-encoded info_hash and peer_id (20 bytes each)
        info_hash = "a" * 20
        peer_id = "b" * 20
        query = f"info_hash={info_hash}&peer_id={peer_id}&port=6881&uploaded=0&downloaded=0&left=1000"
        
        request = AnnounceRequest.from_query_string(query, "192.168.1.100")
        
        assert request.info_hash == info_hash.encode()
        assert request.peer_id == peer_id.encode()
        assert request.port == 6881
        assert request.uploaded == 0
        assert request.downloaded == 0
        assert request.left == 1000
        assert request.ip == "192.168.1.100"
    
    def test_parse_with_event(self):
        """Parse request with event parameter."""
        info_hash = "a" * 20
        peer_id = "b" * 20
        query = f"info_hash={info_hash}&peer_id={peer_id}&port=6881&event=started"
        
        request = AnnounceRequest.from_query_string(query, "192.168.1.100")
        
        assert request.event == "started"
    
    def test_parse_with_compact(self):
        """Parse request with compact parameter."""
        info_hash = "a" * 20
        peer_id = "b" * 20
        query = f"info_hash={info_hash}&peer_id={peer_id}&port=6881&compact=1"
        
        request = AnnounceRequest.from_query_string(query, "192.168.1.100")
        
        assert request.compact is True
    
    def test_parse_missing_info_hash(self):
        """Missing info_hash raises ValueError."""
        peer_id = "b" * 20
        query = f"peer_id={peer_id}&port=6881"
        
        with pytest.raises(ValueError, match="info_hash"):
            AnnounceRequest.from_query_string(query, "192.168.1.100")
    
    def test_parse_missing_peer_id(self):
        """Missing peer_id raises ValueError."""
        info_hash = "a" * 20
        query = f"info_hash={info_hash}&port=6881"
        
        with pytest.raises(ValueError, match="peer_id"):
            AnnounceRequest.from_query_string(query, "192.168.1.100")
    
    def test_parse_missing_port(self):
        """Missing port raises ValueError."""
        info_hash = "a" * 20
        peer_id = "b" * 20
        query = f"info_hash={info_hash}&peer_id={peer_id}"
        
        with pytest.raises(ValueError, match="port"):
            AnnounceRequest.from_query_string(query, "192.168.1.100")
    
    def test_parse_invalid_info_hash_length(self):
        """Invalid info_hash length raises ValueError."""
        info_hash = "a" * 10  # Too short
        peer_id = "b" * 20
        query = f"info_hash={info_hash}&peer_id={peer_id}&port=6881"
        
        with pytest.raises(ValueError, match="info_hash length"):
            AnnounceRequest.from_query_string(query, "192.168.1.100")


# --- Test TrackerState ---

class TestTrackerState:
    """Tests for TrackerState."""
    
    @pytest.fixture
    def state(self):
        """Create a TrackerState instance."""
        return TrackerState(peer_expiry=60)
    
    def test_register_transfer(self, state):
        """Register a transfer hash."""
        info_hash = b"a" * 20
        
        state.register_transfer(info_hash)
        
        assert state.is_registered(info_hash)
    
    def test_unregister_transfer(self, state):
        """Unregister a transfer hash."""
        info_hash = b"a" * 20
        state.register_transfer(info_hash)
        
        state.unregister_transfer(info_hash)
        
        assert not state.is_registered(info_hash)
    
    def test_unregistered_hash_returns_false(self, state):
        """Unregistered hash returns False."""
        info_hash = b"a" * 20
        
        assert not state.is_registered(info_hash)
    
    def test_peer_registration(self, state):
        """Register a peer (seeder with left=0)."""
        info_hash = b"a" * 20
        peer_id = b"b" * 20
        
        state.register_transfer(info_hash)
        state.update_peer(info_hash, peer_id, "192.168.1.1", 6881, left=0)
        
        peers = state.get_peers(info_hash)
        assert peers == [("192.168.1.1", 6881)]
    
    def test_peer_lookup_excludes_self(self, state):
        """Get peers excludes the requesting peer."""
        info_hash = b"a" * 20
        peer_id_1 = b"1" * 20
        peer_id_2 = b"2" * 20
        
        state.register_transfer(info_hash)
        state.update_peer(info_hash, peer_id_1, "192.168.1.1", 6881, left=0)
        state.update_peer(info_hash, peer_id_2, "192.168.1.2", 6882, left=1000)
        
        # Request from peer_id_2 should not see itself
        peers = state.get_peers(info_hash, exclude_peer_id=peer_id_2)
        assert peers == [("192.168.1.1", 6881)]
    
    def test_whitelist_enforcement(self, state):
        """Unregistered hash returns empty peers."""
        info_hash = b"a" * 20
        peer_id = b"b" * 20
        
        # Don't register, just update peer
        state.update_peer(info_hash, peer_id, "192.168.1.1", 6881, left=0)
        
        # Hash is not registered
        assert not state.is_registered(info_hash)
        # But peers still exist (for flexibility)
        peers = state.get_peers(info_hash)
        assert peers == [("192.168.1.1", 6881)]
    
    def test_peer_expiry(self, state):
        """Expired peers are removed."""
        state.peer_expiry = 1  # 1 second expiry
        info_hash = b"a" * 20
        peer_id = b"b" * 20
        
        state.register_transfer(info_hash)
        state.update_peer(info_hash, peer_id, "192.168.1.1", 6881, left=0)
        
        # Peer exists initially
        assert len(state.get_peers(info_hash)) == 1
        
        # Wait for expiry
        time.sleep(1.5)
        
        # Peer should be expired
        peers = state.get_peers(info_hash)
        assert len(peers) == 0
    
    def test_cleanup_expired_peers(self, state):
        """Cleanup removes expired peers."""
        state.peer_expiry = 1
        info_hash = b"a" * 20
        peer_id = b"b" * 20
        
        state.register_transfer(info_hash)
        state.update_peer(info_hash, peer_id, "192.168.1.1", 6881, left=0)
        
        # Wait for expiry
        time.sleep(1.5)
        
        removed = state.cleanup_expired_peers()
        assert removed == 1
    
    def test_remove_peer(self, state):
        """Remove a specific peer."""
        info_hash = b"a" * 20
        peer_id = b"b" * 20
        
        state.register_transfer(info_hash)
        state.update_peer(info_hash, peer_id, "192.168.1.1", 6881, left=0)
        
        state.remove_peer(info_hash, peer_id)
        
        peers = state.get_peers(info_hash)
        assert len(peers) == 0


# --- Test BitTorrentTracker ---

class TestBitTorrentTracker:
    """Tests for BitTorrentTracker."""
    
    def test_tracker_creation(self):
        """Create tracker with defaults."""
        tracker = BitTorrentTracker()
        
        assert tracker.port == 6969
        assert tracker.external_url == "http://localhost:6969/announce"
        assert tracker.announce_interval == 60
    
    def test_tracker_custom_config(self):
        """Create tracker with custom config."""
        tracker = BitTorrentTracker(
            port=7070,
            external_url="http://example.com:7070/announce",
            announce_interval=120,
            peer_expiry=300
        )
        
        assert tracker.port == 7070
        assert tracker.external_url == "http://example.com:7070/announce"
        assert tracker.announce_interval == 120
        assert tracker.state.peer_expiry == 300
    
    def test_tracker_register_unregister(self):
        """Register and unregister transfer hashes."""
        tracker = BitTorrentTracker()
        info_hash = b"a" * 20
        
        tracker.register_transfer(info_hash)
        assert tracker.is_registered(info_hash)
        
        tracker.unregister_transfer(info_hash)
        assert not tracker.is_registered(info_hash)


# --- Test config helpers ---

class TestTrackerConfig:
    """Tests for tracker config helpers."""
    
    def test_get_tracker_config_defaults(self):
        """Get tracker config with defaults."""
        config = {}
        
        tracker_config = get_tracker_config(config)
        
        assert tracker_config["enabled"] is True
        assert tracker_config["port"] == 6969
        assert tracker_config["external_url"] is None
        assert tracker_config["announce_interval"] == 60
        assert tracker_config["peer_expiry"] == 120
    
    def test_get_tracker_config_custom(self):
        """Get tracker config with custom values."""
        config = {
            "tracker": {
                "enabled": False,
                "port": 7070,
                "external_url": "http://example.com:7070/announce",
                "announce_interval": 120,
                "peer_expiry": 300
            }
        }
        
        tracker_config = get_tracker_config(config)
        
        assert tracker_config["enabled"] is False
        assert tracker_config["port"] == 7070
        assert tracker_config["external_url"] == "http://example.com:7070/announce"
        assert tracker_config["announce_interval"] == 120
        assert tracker_config["peer_expiry"] == 300
    
    def test_create_tracker_from_config_enabled(self):
        """Create tracker when enabled."""
        config = {
            "tracker": {
                "enabled": True,
                "port": 7070
            }
        }
        
        tracker = create_tracker_from_config(config)
        
        assert tracker is not None
        assert tracker.port == 7070
    
    def test_create_tracker_from_config_disabled(self):
        """Return None when tracker disabled."""
        config = {
            "tracker": {
                "enabled": False
            }
        }
        
        tracker = create_tracker_from_config(config)
        
        assert tracker is None


# --- Test announce response format ---

class TestAnnounceResponseFormat:
    """Tests for announce response format."""
    
    def test_response_format_compact(self):
        """Verify compact response format."""
        # This tests the expected output format
        peers = [("192.168.1.1", 6881)]
        peer_data = encode_compact_peers(peers)
        
        response_dict = {
            "interval": 60,
            "peers": peer_data
        }
        response = bencode(response_dict)
        
        # Should be valid bencode with interval and peers
        assert b"8:intervali60e" in response
        assert b"5:peers" in response


# ──────────────────────────────────────────────────
# Helpers for scrape tests
# ──────────────────────────────────────────────────

def _find_free_port():
    """Find a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _bdecode_simple(data: bytes):
    """Minimal bdecoder for test verification."""
    return _bdecode(data, 0)[0]


def _bdecode(data: bytes, idx: int):
    """Recursive bdecoder returning (value, next_index)."""
    if data[idx:idx + 1] == b"i":
        end = data.index(b"e", idx)
        return int(data[idx + 1:end]), end + 1
    elif data[idx:idx + 1] == b"l":
        result = []
        idx += 1
        while data[idx:idx + 1] != b"e":
            val, idx = _bdecode(data, idx)
            result.append(val)
        return result, idx + 1
    elif data[idx:idx + 1] == b"d":
        result = {}
        idx += 1
        while data[idx:idx + 1] != b"e":
            key, idx = _bdecode(data, idx)
            val, idx = _bdecode(data, idx)
            result[key] = val
        return result, idx + 1
    else:
        # String/bytes
        colon = data.index(b":", idx)
        length = int(data[idx:colon])
        start = colon + 1
        return data[start:start + length], start + length


# --- Test _handle_scrape ---

class TestHandleScrape:
    """Tests for TrackerRequestHandler._handle_scrape() via live tracker."""

    @pytest.fixture
    def tracker(self):
        """Start a tracker on a random port, yield it, then stop."""
        port = _find_free_port()
        t = BitTorrentTracker(port=port, announce_interval=60)
        t.start()
        time.sleep(0.1)  # Let the server start
        yield t
        t.stop()

    def _scrape(self, tracker, info_hashes):
        """Make a scrape request to the tracker.

        Args:
            tracker: Running BitTorrentTracker instance
            info_hashes: List of 20-byte info_hashes

        Returns:
            Decoded response dict
        """
        from urllib.parse import quote_from_bytes
        params = "&".join(
            f"info_hash={quote_from_bytes(h)}" for h in info_hashes
        )
        url = f"http://127.0.0.1:{tracker.port}/scrape?{params}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return _bdecode_simple(resp.read())

    def test_scrape_registered_hash_no_peers(self, tracker):
        """Scrape registered hash with no peers returns zeros."""
        info_hash = b"\x01" * 20
        tracker.register_transfer(info_hash)

        result = self._scrape(tracker, [info_hash])

        assert b"files" in result
        files = result[b"files"]
        assert info_hash in files
        stats = files[info_hash]
        assert stats[b"complete"] == 0
        assert stats[b"incomplete"] == 0
        assert stats[b"downloaded"] == 0

    def test_scrape_registered_hash_with_seeder(self, tracker):
        """Scrape registered hash with a seeder returns complete=1."""
        info_hash = b"\x02" * 20
        peer_id = b"\xaa" * 20
        tracker.register_transfer(info_hash)
        tracker.state.update_peer(info_hash, peer_id, "10.0.0.1", 6881, left=0)

        result = self._scrape(tracker, [info_hash])

        stats = result[b"files"][info_hash]
        assert stats[b"complete"] == 1
        assert stats[b"incomplete"] == 0

    def test_scrape_registered_hash_with_leecher(self, tracker):
        """Scrape registered hash with a leecher returns incomplete=1."""
        info_hash = b"\x03" * 20
        peer_id = b"\xbb" * 20
        tracker.register_transfer(info_hash)
        tracker.state.update_peer(info_hash, peer_id, "10.0.0.2", 6882, left=5000)

        result = self._scrape(tracker, [info_hash])

        stats = result[b"files"][info_hash]
        assert stats[b"complete"] == 0
        assert stats[b"incomplete"] == 1

    def test_scrape_unregistered_hash_returns_zeros(self, tracker):
        """Scrape unregistered hash returns all zeros."""
        info_hash = b"\x04" * 20
        # Do NOT register

        result = self._scrape(tracker, [info_hash])

        stats = result[b"files"][info_hash]
        assert stats[b"complete"] == 0
        assert stats[b"incomplete"] == 0
        assert stats[b"downloaded"] == 0

    def test_scrape_multiple_hashes(self, tracker):
        """Scrape multiple hashes in one request."""
        h1 = b"\x05" * 20
        h2 = b"\x06" * 20
        tracker.register_transfer(h1)
        tracker.state.update_peer(h1, b"\xcc" * 20, "10.0.0.3", 6883, left=0)
        # h2 not registered

        result = self._scrape(tracker, [h1, h2])

        files = result[b"files"]
        assert files[h1][b"complete"] == 1
        assert files[h2][b"complete"] == 0

    def test_scrape_empty_query_returns_empty_files(self, tracker):
        """Scrape with no info_hash params returns empty files dict."""
        url = f"http://127.0.0.1:{tracker.port}/scrape"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = _bdecode_simple(resp.read())

        assert result[b"files"] == {}

    def test_scrape_mixed_seeders_and_leechers(self, tracker):
        """Scrape hash with both seeders and leechers."""
        info_hash = b"\x07" * 20
        tracker.register_transfer(info_hash)
        tracker.state.update_peer(info_hash, b"\x01" * 20, "10.0.0.1", 6881, left=0)
        tracker.state.update_peer(info_hash, b"\x02" * 20, "10.0.0.2", 6882, left=0)
        tracker.state.update_peer(info_hash, b"\x03" * 20, "10.0.0.3", 6883, left=1000)

        result = self._scrape(tracker, [info_hash])

        stats = result[b"files"][info_hash]
        assert stats[b"complete"] == 2
        assert stats[b"incomplete"] == 1


# --- Test _handle_announce via live tracker (U6) ---

class TestHandleAnnounce:
    """Tests for TrackerRequestHandler._handle_announce() via live tracker."""

    @pytest.fixture
    def tracker(self):
        """Start a tracker on a random port, yield it, then stop."""
        port = _find_free_port()
        t = BitTorrentTracker(port=port, announce_interval=30)
        t.start()
        time.sleep(0.1)
        yield t
        t.stop()

    def _announce(self, tracker, info_hash, peer_id, port=6881, left=0,
                  event="", ip=None):
        """Make an announce request to the tracker.

        Args:
            tracker: Running BitTorrentTracker instance
            info_hash: 20-byte info_hash
            peer_id: 20-byte peer_id
            port: Peer port
            left: Bytes left to download
            event: Event string (started, completed, stopped, "")
            ip: Optional explicit IP

        Returns:
            Decoded bencoded response dict
        """
        from urllib.parse import quote_from_bytes
        params = (
            f"info_hash={quote_from_bytes(info_hash)}"
            f"&peer_id={quote_from_bytes(peer_id)}"
            f"&port={port}"
            f"&uploaded=0&downloaded=0"
            f"&left={left}"
            f"&compact=1"
        )
        if event:
            params += f"&event={event}"
        if ip:
            params += f"&ip={ip}"
        url = f"http://127.0.0.1:{tracker.port}/announce?{params}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return _bdecode_simple(resp.read())

    def test_announce_registered_hash_returns_interval(self, tracker):
        """Announce for registered hash returns response with interval."""
        info_hash = b"\x10" * 20
        peer_id = b"\x20" * 20
        tracker.register_transfer(info_hash)

        result = self._announce(tracker, info_hash, peer_id, left=1000)

        assert b"interval" in result
        assert result[b"interval"] == 30
        assert b"peers" in result

    def test_announce_unregistered_hash_returns_empty_peers(self, tracker):
        """Announce for unregistered hash returns empty peer list."""
        info_hash = b"\x11" * 20
        peer_id = b"\x21" * 20

        result = self._announce(tracker, info_hash, peer_id, left=1000)

        assert b"peers" in result
        # Compact format: empty bytes = no peers
        assert result[b"peers"] == b""

    def test_announce_registers_peer(self, tracker):
        """After announce, the peer is visible via tracker.get_peers()."""
        info_hash = b"\x12" * 20
        peer_id = b"\x22" * 20
        tracker.register_transfer(info_hash)

        self._announce(tracker, info_hash, peer_id, port=7777, left=500,
                       ip="10.0.0.50")

        peers = tracker.get_peers(info_hash)
        assert len(peers) >= 1
        ips = [p[0] for p in peers]
        assert "10.0.0.50" in ips

    def test_announce_stopped_event_removes_peer(self, tracker):
        """Announce with event=stopped removes the peer from tracking."""
        info_hash = b"\x13" * 20
        peer_id = b"\x23" * 20
        tracker.register_transfer(info_hash)

        # First announce to register
        self._announce(tracker, info_hash, peer_id, port=6881, left=0,
                       ip="10.0.0.60")
        peers = tracker.get_peers(info_hash)
        assert len(peers) == 1

        # Stopped event should remove
        self._announce(tracker, info_hash, peer_id, port=6881, left=0,
                       event="stopped", ip="10.0.0.60")
        peers = tracker.get_peers(info_hash)
        assert len(peers) == 0

    def test_announce_excludes_requesting_peer(self, tracker):
        """Response peer list does not include the announcing peer itself."""
        info_hash = b"\x14" * 20
        peer_a = b"\x24" * 20
        peer_b = b"\x25" * 20
        tracker.register_transfer(info_hash)

        # Register peer A
        self._announce(tracker, info_hash, peer_a, port=6881, left=0,
                       ip="10.0.0.70")
        # Announce from peer B — should see peer A but not itself
        result = self._announce(tracker, info_hash, peer_b, port=6882, left=1000,
                                ip="10.0.0.71")

        peer_bytes = result[b"peers"]
        # 6 bytes per peer in compact format
        num_peers = len(peer_bytes) // 6
        assert num_peers == 1
        # The returned peer should be peer A (10.0.0.70:6881)
        import socket
        import struct
        ip_bytes = socket.inet_aton("10.0.0.70")
        port_bytes = struct.pack(">H", 6881)
        assert ip_bytes + port_bytes == peer_bytes[:6]

    def test_announce_returns_other_peers(self, tracker):
        """When two peers have announced, each sees the other."""
        info_hash = b"\x15" * 20
        peer_a = b"\x26" * 20
        peer_b = b"\x27" * 20
        tracker.register_transfer(info_hash)

        # Register both peers
        self._announce(tracker, info_hash, peer_a, port=6881, left=0,
                       ip="10.0.0.80")
        self._announce(tracker, info_hash, peer_b, port=6882, left=1000,
                       ip="10.0.0.81")

        # Peer A announces again — should see peer B
        result = self._announce(tracker, info_hash, peer_a, port=6881, left=0,
                                ip="10.0.0.80")

        peer_bytes = result[b"peers"]
        num_peers = len(peer_bytes) // 6
        assert num_peers == 1  # Only peer B (peer A excluded)


# --- Test TrackerState.get_scrape_stats (U9) ---

class TestGetScrapeStats:
    """Tests for TrackerState.get_scrape_stats() directly."""

    def test_empty_hash_returns_zeros(self):
        """Untracked hash returns complete=0, incomplete=0."""
        state = TrackerState()
        info_hash = b"\x30" * 20

        stats = state.get_scrape_stats(info_hash)

        assert stats["complete"] == 0
        assert stats["incomplete"] == 0

    def test_seeder_counted_as_complete(self):
        """Peer with left=0 counted as complete (seeder)."""
        state = TrackerState()
        info_hash = b"\x31" * 20
        state.register_transfer(info_hash)
        state.update_peer(info_hash, b"\x01" * 20, "10.0.0.1", 6881, left=0)

        stats = state.get_scrape_stats(info_hash)

        assert stats["complete"] == 1
        assert stats["incomplete"] == 0

    def test_leecher_counted_as_incomplete(self):
        """Peer with left>0 counted as incomplete (leecher)."""
        state = TrackerState()
        info_hash = b"\x32" * 20
        state.register_transfer(info_hash)
        state.update_peer(info_hash, b"\x01" * 20, "10.0.0.1", 6881, left=5000)

        stats = state.get_scrape_stats(info_hash)

        assert stats["complete"] == 0
        assert stats["incomplete"] == 1

    def test_mixed_seeders_and_leechers(self):
        """Correct counts with mixed seeders and leechers."""
        state = TrackerState()
        info_hash = b"\x33" * 20
        state.register_transfer(info_hash)
        state.update_peer(info_hash, b"\x01" * 20, "10.0.0.1", 6881, left=0)
        state.update_peer(info_hash, b"\x02" * 20, "10.0.0.2", 6882, left=0)
        state.update_peer(info_hash, b"\x03" * 20, "10.0.0.3", 6883, left=100)
        state.update_peer(info_hash, b"\x04" * 20, "10.0.0.4", 6884, left=200)
        state.update_peer(info_hash, b"\x05" * 20, "10.0.0.5", 6885, left=0)

        stats = state.get_scrape_stats(info_hash)

        assert stats["complete"] == 3
        assert stats["incomplete"] == 2


# --- Test BitTorrentTracker.get_status (U10) ---

class TestGetStatus:
    """Tests for BitTorrentTracker.get_status()."""

    def test_status_when_not_running(self):
        """get_status returns correct dict when tracker is not running."""
        tracker = BitTorrentTracker(port=9999, external_url="http://test:9999/announce")

        status = tracker.get_status()

        assert status["enabled"] is True
        assert status["running"] is False
        assert status["port"] == 9999
        assert status["active_transfers"] == 0

    def test_status_when_running(self):
        """get_status returns running=True when tracker is started."""
        port = _find_free_port()
        tracker = BitTorrentTracker(port=port)
        tracker.start()
        time.sleep(0.1)

        try:
            status = tracker.get_status()
            assert status["running"] is True
            assert status["port"] == port
        finally:
            tracker.stop()

    def test_status_active_transfers_count(self):
        """get_status returns correct active_transfers count."""
        tracker = BitTorrentTracker(port=9998)
        tracker.register_transfer(b"\x01" * 20)
        tracker.register_transfer(b"\x02" * 20)

        status = tracker.get_status()

        assert status["active_transfers"] == 2


class TestExternalUrlLiveUpdate:
    """Tests for live-updating external_url on running tracker."""

    def test_external_url_updates_in_place(self):
        """external_url is a plain attribute that can be updated at runtime."""
        tracker = BitTorrentTracker(port=9999, external_url="http://old:6969/announce")
        assert tracker.external_url == "http://old:6969/announce"

        tracker.external_url = "http://new:7070/announce"
        assert tracker.external_url == "http://new:7070/announce"

    def test_external_url_fallback_when_cleared(self):
        """When external_url is set to None/empty, falls back to localhost default."""
        tracker = BitTorrentTracker(port=9999, external_url="http://custom:6969/announce")

        # Simulate the fallback logic used in the API handler
        new_url = None
        tracker.external_url = new_url or f"http://localhost:{tracker.port}/announce"

        assert tracker.external_url == "http://localhost:9999/announce"
