from enum import Enum

class TorrentState(Enum):
    RADARR_QUEUED = 0
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

    def __init__(self, name=None, id=None, state=None, radarr_info=None, 
                 home_client=None, target_client=None,
                 home_client_info=None, home_client_name=None, target_client_info=None, 
                 target_client_name=None, save_callback=None):
        self.name = name
        self.id = id
        self.state = state
        self.radarr_info = radarr_info
        self.home_client = home_client
        self.home_client_name = home_client_name
        self.home_client_info = home_client_info
        self.target_client = target_client
        self.target_client_name = target_client_name
        self.target_client_info = target_client_info
        self.save_callback = save_callback
        self.progress = 0
        self.current_file = ""
        self.current_file_count = 0
        self.total_files = 0

    def set_home_client_info(self, home_client_info):
        self.home_client_info = home_client_info

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
        return {
            "name": self.name,
            "id": self.id,
            "state": self.state.name if self.state else None,
            "home_client_name": self.home_client_name,
            "home_client_info": self.home_client_info,
            "target_client_info": self.target_client_info,
            "target_client_name": self.target_client_name,
            "progress": self.progress,
            "current_file": self.current_file,
            "current_file_count": self.current_file_count,
            "total_files": self.total_files,
        }

    @classmethod
    def from_dict(cls, data, download_clients, save_callback=None):
        """Create a Torrent object from a dictionary."""
        torrent = cls(
            name=data.get("name"),
            id=data.get("id"),
            state=TorrentState[data["state"]] if data.get("state") else None,
            radarr_info=data.get("radarr_info"),
            home_client=download_clients.get(data.get("home_client_name")),
            home_client_info=data.get("home_client_info"),
            home_client_name=data.get("home_client_name"),
            target_client=download_clients.get(data.get("target_client_name")),
            target_client_info=data.get("target_client_info"),
            target_client_name=data.get("target_client_name"),
            save_callback=save_callback,
        )
        torrent.progress = data.get("progress", 0)
        torrent.current_file = data.get("current_file", "")
        torrent.current_file_count = data.get("current_file_count", 0)
        torrent.total_files = data.get("total_files", 0)
        return torrent
