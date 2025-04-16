import radarr
import logging
from transferarr.models.torrent import Torrent, TorrentState

logger = logging.getLogger(__name__)

def radrr_torrent_ready_to_remove(config, torrent):
    '''Check if the torrent is in the Radarr queue and ready to be removed.'''
    try:
        with radarr.ApiClient(config) as radarr_api_client:
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
                logger.error(f"Exception when calling QueueApi->get_queue: {e}")
    except Exception as e:
        logger.error(f"Exception when creating radarr client: {e}")
    return False

def get_radarr_queue_updates(config, torrents, save_torrents_state):

    ### TODO: If connection fails, try again after a delay
    try:
        with radarr.ApiClient(config) as radarr_api_client:
            api_instance = radarr.QueueApi(radarr_api_client)
            try:
                api_response = api_instance.get_queue()
                radarr_queue = api_response
                for item in radarr_queue.records:
                    match = None
                    for torrent in torrents:
                        # if item.title == torrent.name:
                        #     match = torrent
                        #     break
                        if item.download_id.lower() == torrent.id.lower():
                            match = torrent
                            break
                    if match is None:
                        new_torrent = Torrent(
                            name=item.title,
                            id = item.download_id.lower(),
                            radarr_info=item,
                            save_callback=save_torrents_state
                        )
                        new_torrent.state = TorrentState.RADARR_QUEUED
                        torrents.append(new_torrent)
                        logger.info(f"New torrent: {item.title}")
                    else:
                        match.radarr_info = item
            except Exception as e:
                logger.error(f"Exception when calling QueueApi->get_queue: {e}")
    except Exception as e:
        logger.error(f"Exception when creating radarr client: {e}")
