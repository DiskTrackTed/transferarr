from transferarr.clients.deluge import DelugeClient

def load_download_clients(config):
    """
    Load download clients based on the provided configuration.

    Args:
        config (dict): Configuration dictionary containing client settings.
    Returns:
        dict: Dict of initialized download client instances.
    """
    download_clients = {}
    for download_client in config["download_clients"].keys():
        download_client_config = config["download_clients"][download_client]
        if download_client_config["type"] == "deluge":
            download_clients[download_client] = DelugeClient(
                download_client,
                download_client_config["host"],
                download_client_config["port"],
                download_client_config["username"],
                download_client_config["password"]
            )

    return download_clients