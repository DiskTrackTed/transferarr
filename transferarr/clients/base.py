from transferarr.clients.registry import ClientRegistry
from transferarr.clients.config import ClientConfig

# Import deluge module to register the client
import transferarr.clients.deluge  # noqa: F401


def load_download_clients(config):
    """
    Load download clients based on the provided configuration.

    Args:
        config (dict): Configuration dictionary containing client settings.
    Returns:
        dict: Dict of initialized download client instances.
    """
    download_clients = {}
    for name, client_config in config["download_clients"].items():
        config_obj = ClientConfig.from_dict(name, client_config)
        download_clients[name] = ClientRegistry.create(config_obj)

    return download_clients