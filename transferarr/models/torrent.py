import copy
from enum import Enum

class TorrentState(Enum):
    MANAGER_QUEUED = 0
    UNCLAIMED = 1
    HOME_QUEUED = 2
    HOME_CHECKING = 3
    HOME_ALLOCATING = 4
    HOME_DOWNLOADING = 5
    HOME_SEEDING = 6
    HOME_PAUSED = 7
    HOME_MOVING = 8
    HOME_ERROR = 9
    COPYING = 10
    COPIED = 11
    TARGET_QUEUED = 12
    TARGET_CHECKING = 13
    TARGET_ALLOCATING = 14
    TARGET_DOWNLOADING = 15
    TARGET_SEEDING = 16
    TARGET_PAUSED = 17
    TARGET_MOVING = 18
    TARGET_ERROR = 19
    ERROR = 20
    MISSING = 21
    TORRENT_CREATE_QUEUE = 29
    TORRENT_CREATING = 30
    TORRENT_TARGET_ADDING = 31
    TORRENT_DOWNLOADING = 32
    TORRENT_SEEDING = 33
    TRANSFER_FAILED = 34  # Failed after max retries, requires user action

class Torrent:
    _state = None
    save_callback = None
    not_found_attempts = 0

    def __init__(self, name=None, id=None, state=None, 
                 home_client=None, target_client=None,
                 home_client_info=None, home_client_name=None, target_client_info=None, 
                 target_client_name=None, save_callback=None, media_manager=None,
                 transfer=None, _transfer_id=None, delete_source_cross_seeds=None):
        self.name = name
        self.id = id
        self.state = state
        self.home_client = home_client
        self.home_client_name = home_client_name
        self.home_client_info = home_client_info
        self.target_client = target_client
        self.target_client_name = target_client_name
        self.target_client_info = target_client_info
        self.save_callback = save_callback
        self.media_manager = media_manager
        self.size = 0
        self.progress = 0
        self.transfer_speed = 0
        self.current_file = ""
        self.current_file_count = 0
        self.total_files = 0
        self.transfer = transfer  # dict with hash, name, retry_count, etc.
        self._transfer_id = _transfer_id  # History service transfer ID
        self.delete_source_cross_seeds = delete_source_cross_seeds  # Whether to remove cross-seed siblings on source removal

    def set_home_client_info(self, home_client_info):
        self.home_client_info = home_client_info
        self.size = int(home_client_info.get("total_size", 0))

    def set_progress_from_home_client_info(self):
        if self.home_client_info:
            self.progress = int(self.home_client_info.get("progress", 0))
        else:
            self.progress = 0

    def set_target_client_info(self, target_client_info):
        self.target_client_info = target_client_info

    def set_home_client(self, client):
        self.home_client = client
        self.home_client_name = client.name

    def set_target_client(self, client):
        self.target_client = client
        self.target_client_name = client.name

    def __str__(self):
        return f"{self.name} - {self.id}: - {self.state.name if self.state else None}"

    @property
    def _is_torrent_transfer_state(self) -> bool:
        """Whether the torrent is currently in a torrent-based transfer state."""
        return self.state is not None and self.state.name.startswith("TORRENT_")

    @property
    def media_manager_type(self):
        """Get the media manager type string ('radarr', 'sonarr', or None)."""
        if not self.media_manager:
            return None
        manager_class = type(self.media_manager).__name__
        if 'Radarr' in manager_class:
            return 'radarr'
        elif 'Sonarr' in manager_class:
            return 'sonarr'
        return None

    @property
    def state(self):
        return self._state

    def mark_dirty(self):
        if self.save_callback:
            self.save_callback()

    @state.setter
    def state(self, value):
        self._state = value
        self.mark_dirty()

    def to_dict(self):
        """Convert the Torrent object to a dictionary."""
        result = {
            "name": self.name,
            "id": self.id,
            "state": self.state.name if self.state else None,
            "home_client_name": self.home_client_name,
            "home_client_info": self.home_client_info,
            "target_client_info": self.target_client_info,
            "target_client_name": self.target_client_name,
            "progress": self._get_display_progress(),
            "size": self._get_display_size(),
            "transfer_speed": self._get_display_transfer_speed(),
            "current_file": self.current_file,
            "current_file_count": self.current_file_count,
            "total_files": self.total_files,
            "media_manager_type": self.media_manager_type,
        }
        
        # Include transfer data if present (for torrent-based transfers)
        if self.transfer:
            result["transfer"] = self.transfer
        
        # Include history transfer ID if present (survives restarts)
        if self._transfer_id is not None:
            result["_transfer_id"] = self._transfer_id
        
        # Include cross-seed deletion flag if explicitly set
        if self.delete_source_cross_seeds is not None:
            result["delete_source_cross_seeds"] = self.delete_source_cross_seeds
        
        return result

    def to_persisted_dict(self):
        """Convert the Torrent object to a persistence-safe dictionary.

        The save worker runs on a separate thread, so persisted data must not
        retain references to mutable nested dicts that other threads continue
        mutating.
        """
        result = self.to_dict()
        for key in ("home_client_info", "target_client_info", "transfer"):
            if result.get(key) is not None:
                result[key] = copy.deepcopy(result[key])
        return result
    
    def _get_display_progress(self) -> int:
        """Get the progress value to display in the API.
        
        For torrent-based transfers (TORRENT_* states), use transfer progress.
        Otherwise, use home client progress.
        """
        if self._is_torrent_transfer_state:
            if self.transfer:
                bytes_downloaded = self.transfer.get("bytes_downloaded", 0)
                total_size = self.transfer.get("total_size", 0)
                if total_size > 0:
                    return int((bytes_downloaded / total_size) * 100)
                return 0
        return self.progress
    
    def _get_display_size(self) -> int:
        """Get the size value to display in the API.
        
        For torrent-based transfers (TORRENT_* states), use transfer total_size.
        Otherwise, use home client size.
        """
        if self._is_torrent_transfer_state:
            if self.transfer and self.transfer.get("total_size"):
                return self.transfer.get("total_size", 0)
        return self.size
    
    def _get_display_transfer_speed(self) -> float:
        """Get the transfer speed to display in the API.
        
        For torrent-based transfers (TORRENT_* states), use transfer download_rate.
        Otherwise, use SFTP transfer speed.
        """
        if self._is_torrent_transfer_state:
            if self.transfer:
                return self.transfer.get("download_rate", 0)
        return self.transfer_speed

    @classmethod
    def from_dict(cls, data, download_clients, media_managers=None, save_callback=None):
        """Create a Torrent object from a dictionary.
        
        Args:
            data: Dictionary with torrent data
            download_clients: Dict of download client name -> client instance
            media_managers: List of media manager instances (RadarrManager, SonarrManager)
            save_callback: Callback function to save state
        """
        # Restore media_manager from type if available
        media_manager = None
        media_manager_type = data.get("media_manager_type")
        if media_manager_type and media_managers:
            for mm in media_managers:
                manager_class = type(mm).__name__
                if media_manager_type == 'radarr' and 'Radarr' in manager_class:
                    media_manager = mm
                    break
                elif media_manager_type == 'sonarr' and 'Sonarr' in manager_class:
                    media_manager = mm
                    break
        
        torrent = cls(
            name=data.get("name"),
            id=data.get("id"),
            state=TorrentState[data["state"]] if data.get("state") else None,
            home_client=download_clients.get(data.get("home_client_name")),
            home_client_info=data.get("home_client_info"),
            home_client_name=data.get("home_client_name"),
            target_client=download_clients.get(data.get("target_client_name")),
            target_client_info=data.get("target_client_info"),
            target_client_name=data.get("target_client_name"),
            save_callback=save_callback,
            media_manager=media_manager,
            transfer=data.get("transfer"),  # Restore transfer data if present
            _transfer_id=data.get("_transfer_id"),  # Restore history transfer ID
            delete_source_cross_seeds=data.get("delete_source_cross_seeds"),  # Restore cross-seed flag
        )
        torrent.transfer_speed = data.get("transfer_speed", 0)
        torrent.progress = data.get("progress", 0)
        torrent.size = data.get("size", 0)
        torrent.current_file = data.get("current_file", "")
        torrent.current_file_count = data.get("current_file_count", 0)
        torrent.total_files = data.get("total_files", 0)
        return torrent
