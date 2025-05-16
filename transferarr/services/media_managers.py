import radarr
import sonarr
import logging
from transferarr.models.torrent import Torrent, TorrentState


class RadarrManager:
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        host = self.config["host"]
        if "port" in self.config:
            host = f"{host}:{self.config['port']}"
        self.radarr_config = radarr.Configuration(
            host=host,
        )
        self.radarr_config.api_key['apikey'] = self.config["api_key"]
        self.radarr_config.api_key['X-Api-Key'] = self.config["api_key"]
        self.test_api_client()

    def test_api_client(self):
        try:
            with radarr.ApiClient(self.radarr_config) as radarr_api_client:
                api_instance = radarr.QueueApi(radarr_api_client)
                api_response = api_instance.get_queue()
                return True
        except Exception as e:
            self.logger.error(f"Exception when creating radarr client: {e}")
            return False
        

    def get_queue_updates(self, torrents, save_torrents_state):
        ### TODO: If connection fails, try again after a delay
        try:
            with radarr.ApiClient(self.radarr_config) as radarr_api_client:
                api_instance = radarr.QueueApi(radarr_api_client)
                try:
                    api_response = api_instance.get_queue()
                    radarr_queue = api_response
                    for item in radarr_queue.records:
                        match = None
                        for torrent in torrents:
                            if item.download_id.lower() == torrent.id.lower():
                                match = torrent
                                break
                        if match is None:
                            new_torrent = Torrent(
                                name=item.title,
                                id = item.download_id.lower(),
                                save_callback=save_torrents_state,
                                media_manager=self
                            )
                            new_torrent.state = TorrentState.MANAGER_QUEUED
                            torrents.append(new_torrent)
                            self.logger.info(f"New torrent: {item.title}")
                        else:
                            match.media_manager = self
                except Exception as e:
                    self.logger.error(f"Exception when calling radarr QueueApi->get_queue: {e}")
        except Exception as e:
            self.logger.error(f"Exception when creating radarr client: {e}")

    def torrent_ready_to_remove(self, torrent):
        '''Check if the torrent is in the Radarr queue and ready to be removed.'''
        self.logger.debug(f"Checking if torrent {torrent.name} is ready to be removed from Radarr") 
        try:
            with radarr.ApiClient(self.radarr_config) as radarr_api_client:
                ready = True
                api_instance = radarr.QueueApi(radarr_api_client)
                try:
                    api_response = api_instance.get_queue()
                    radarr_queue = api_response
                    for item in radarr_queue.records:
                        if item.download_id == torrent.id:
                            ready = False
                    return ready
                except Exception as e:
                    self.logger.error(f"Exception when calling radarr QueueApi->get_queue: {e}")
        except Exception as e:
            self.logger.error(f"Exception when creating radarr client: {e}")
        return False
    

class SonarrManager:
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        host = self.config["host"]
        if "port" in self.config:
            host = f"{host}:{self.config['port']}"
        self.sonarr_config = sonarr.Configuration(
            host=host,
        )
        self.sonarr_config.api_key['apikey'] = self.config["api_key"]
        self.sonarr_config.api_key['X-Api-Key'] = self.config["api_key"]
        self.test_api_client()

    def test_api_client(self):
        try:
            with sonarr.ApiClient(self.sonarr_config) as sonarr_api_client:
                api_instance = sonarr.QueueApi(sonarr_api_client)
                api_response = api_instance.get_queue()
                return True
        except Exception as e:
            self.logger.error(f"Exception when creating sonarr client: {e}")
            return False
        

    def get_queue_updates(self, torrents, save_torrents_state):
        ### TODO: If connection fails, try again after a delay
        try:
            with sonarr.ApiClient(self.sonarr_config) as sonarr_api_client:
                api_instance = sonarr.QueueApi(sonarr_api_client)
                try:
                    api_response = api_instance.get_queue()
                    sonarr_queue = api_response
                    for item in sonarr_queue.records:
                        match = None
                        for torrent in torrents:
                            if item.download_id.lower() == torrent.id.lower():
                                match = torrent
                                break
                        if match is None:
                            new_torrent = Torrent(
                                name=item.title,
                                id = item.download_id.lower(),
                                save_callback=save_torrents_state,
                                media_manager=self
                            )
                            new_torrent.state = TorrentState.MANAGER_QUEUED
                            torrents.append(new_torrent)
                            self.logger.info(f"New torrent: {item.title}")
                        else:
                            match.media_manager = self
                except Exception as e:
                    self.logger.error(f"Exception when calling sonarr QueueApi->get_queue : {e}")
        except Exception as e:
            self.logger.error(f"Exception when creating sonarr client: {e}")

    def torrent_ready_to_remove(self, torrent):
        '''Check if the torrent is in the Sonarr queue and ready to be removed.'''
        self.logger.debug(f"Checking if torrent {torrent.name} is ready to be removed from Sonarr") 
        try:
            with sonarr.ApiClient(self.sonarr_config) as sonarr_api_client:
                ready = True
                api_instance = sonarr.QueueApi(sonarr_api_client)
                try:
                    api_response = api_instance.get_queue()
                    sonarr_queue = api_response
                    for item in sonarr_queue.records:
                        if item.download_id == torrent.id:
                            ready = False
                    return ready
                except Exception as e:
                    self.logger.error(f"Exception when calling sonarr QueueApi->get_queue: {e}")
        except Exception as e:
            self.logger.error(f"Exception when creating sonarr client: {e}")
        return False