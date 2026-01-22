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

class Torrent:
    _state = None
    save_callback = None
    not_found_attempts = 0

    def __init__(self, name=None, id=None, state=None, 
                 home_client=None, target_client=None,
                 home_client_info=None, home_client_name=None, target_client_info=None, 
                 target_client_name=None, save_callback=None, media_manager=None):
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
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value
        if self.save_callback:
            self.save_callback()

    def to_dict(self):
        """Convert the Torrent object to a dictionary."""
        # Determine media_manager_type from the media_manager instance
        media_manager_type = None
        if self.media_manager:
            manager_class = type(self.media_manager).__name__
            if 'Radarr' in manager_class:
                media_manager_type = 'radarr'
            elif 'Sonarr' in manager_class:
                media_manager_type = 'sonarr'
        
        return {
            "name": self.name,
            "id": self.id,
            "state": self.state.name if self.state else None,
            "home_client_name": self.home_client_name,
            "home_client_info": self.home_client_info,
            "target_client_info": self.target_client_info,
            "target_client_name": self.target_client_name,
            "progress": self.progress,
            "size": self.size,
            "transfer_speed": self.transfer_speed,
            "current_file": self.current_file,
            "current_file_count": self.current_file_count,
            "total_files": self.total_files,
            "media_manager_type": media_manager_type,
        }

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
        )
        torrent.transfer_speed = data.get("transfer_speed", 0)
        torrent.progress = data.get("progress", 0)
        torrent.size = data.get("size", 0)
        torrent.current_file = data.get("current_file", "")
        torrent.current_file_count = data.get("current_file_count", 0)
        torrent.total_files = data.get("total_files", 0)
        return torrent
