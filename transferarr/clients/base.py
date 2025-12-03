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
                username=download_client_config.get("username", None),
                password=download_client_config["password"],
                connection_type=download_client_config.get("connection_type", "rpc")
            )

    return download_clients