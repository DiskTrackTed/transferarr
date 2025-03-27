from enum import Enum

class TorrentState(Enum):
    RADARR_QUEUED = 0
    LOCAL_DOWNLOADING = 1
    LOCAL_PAUSED = 2
    LOCAL_SEEDING = 3
    COPYING = 4
    COPIED = 5
    SB_SEEDING = 6
    ERROR = 7
    MISSING = 8

class Torrent:
    _state = None
    save_callback = None

    def __init__(self, name=None, id=None, state=None, radarr_info=None, local_deluge_info=None, sb_deluge_info=None, dot_torrent_file_path=None, save_callback=None):
        self.name = name
        self.id = id
        self.state = state
        self.radarr_info = radarr_info
        self.local_deluge_info = local_deluge_info
        self.sb_deluge_info = sb_deluge_info
        self.dot_torrent_file_path = dot_torrent_file_path
        self.save_callback = save_callback

    def __str__(self):
        return f"{self.name} - {self.id}"

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
            # "radarr_info": self.radarr_info,
            "local_deluge_info": self.local_deluge_info,
            "sb_deluge_info": self.sb_deluge_info,
            "dot_torrent_file_path": self.dot_torrent_file_path,
        }

    @classmethod
    def from_dict(cls, data, save_callback=None):
        """Create a Torrent object from a dictionary."""
        return cls(
            name=data.get("name"),
            id=data.get("id"),
            state=TorrentState[data["state"]] if data.get("state") else None,
            radarr_info=data.get("radarr_info"),
            local_deluge_info=data.get("local_deluge_info"),
            sb_deluge_info=data.get("sb_deluge_info"),
            dot_torrent_file_path=data.get("dot_torrent_file_path"),
            save_callback=save_callback,
        )
