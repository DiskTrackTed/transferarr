"""
Settings page object for UI testing.

The settings page displays:
- Download Clients tab with client management
- Connections tab with transfer connection management
"""
from playwright.sync_api import Page, expect
from .base_page import BasePage


class SettingsPage(BasePage):
    """Page object for the Settings page."""
    
    # Tab selectors
    SETTINGS_TABS = "#settings-tabs"
    TAB_CLIENTS = ".client-tab[data-tab='download-clients']"
    TAB_CONNECTIONS = ".client-tab[data-tab='connections']"
    TAB_CONTENT_CLIENTS = "#download-clients-tab-content"
    TAB_CONTENT_CONNECTIONS = "#connections-tab-content"
    
    # Client management selectors
    ADD_CLIENT_BTN = "#addClientBtn"
    CLIENTS_LIST = "#clientsList"
    CLIENT_CARD = ".client-card"
    LOADING_CLIENTS = "#loadingClients"
    
    # Client modal selectors (from partials/modals/client_modal.html)
    CLIENT_MODAL = "#clientModal"
    CLIENT_FORM = "#clientForm"
    CLIENT_NAME_INPUT = "#clientName"
    CLIENT_HOST_INPUT = "#clientHost"
    CLIENT_PORT_INPUT = "#clientPort"
    CLIENT_USERNAME_INPUT = "#clientUsername"
    CLIENT_PASSWORD_INPUT = "#clientPassword"
    CLIENT_TYPE_SELECT = "#clientType"
    CLIENT_CONNECTION_TYPE_SELECT = "#clientConnectionType"
    SAVE_CLIENT_BTN = "#saveClientBtn"
    TEST_CONNECTION_BTN = "#testConnectionBtn"
    
    # Connection management selectors
    ADD_CONNECTION_BTN = "#addConnectionBtn"
    CONNECTIONS_LIST = "#connectionsList"
    CONNECTION_CARD = ".connection-card"
    LOADING_CONNECTIONS = "#loadingConnections"
    
    # Connection modal selectors (from partials/modals/connection_modal.html)
    CONNECTION_MODAL = "#connectionModal"
    CONNECTION_FORM = "#connectionForm"
    CONNECTION_NAME = "#connectionName"
    CONNECTION_FROM_SELECT = "#fromClient"
    CONNECTION_TO_SELECT = "#toClient"
    CONNECTION_FROM_TYPE = "#fromType"
    CONNECTION_TO_TYPE = "#toType"
    SAVE_CONNECTION_BTN = "#saveConnectionBtn"
    TEST_CONNECTION_BTN2 = "#testConnectionBtn2"
    
    # SFTP config fields
    FROM_SFTP_HOST = "#fromSftpHost"
    FROM_SFTP_PORT = "#fromSftpPort"
    FROM_SFTP_USERNAME = "#fromSftpUsername"
    FROM_SFTP_PASSWORD = "#fromSftpPassword"
    TO_SFTP_HOST = "#toSftpHost"
    TO_SFTP_PORT = "#toSftpPort"
    TO_SFTP_USERNAME = "#toSftpUsername"
    TO_SFTP_PASSWORD = "#toSftpPassword"
    
    # Path config fields
    SOURCE_DOT_TORRENT_PATH = "#sourceDotTorrentPath"
    SOURCE_DOWNLOAD_PATH = "#sourceTorrentDownloadPath"
    DEST_TMP_PATH = "#destinationDotTorrentTmpDir"
    DEST_DOWNLOAD_PATH = "#destinationTorrentDownloadPath"
    
    # Tab content visibility selectors (aliases for clarity)
    CLIENTS_CONTENT = "#download-clients-tab-content"
    CONNECTIONS_CONTENT = "#connections-tab-content"
    
    # Delete modal selectors (from partials/modals/delete_modal.html)
    DELETE_MODAL = "#deleteModal"
    DELETE_CLIENT_NAME = "#deleteClientName"
    CONFIRM_DELETE_BTN = "#confirmDeleteBtn"
    
    def __init__(self, page: Page, base_url: str):
        super().__init__(page, base_url)
    
    def goto(self) -> None:
        """Navigate to settings page and verify it loaded."""
        super().goto("/settings")
        expect(self.page.locator(".card-title").first).to_have_text("Settings")
    
    # ========== Tab Navigation ==========
    
    def switch_to_clients_tab(self) -> None:
        """Switch to Download Clients tab."""
        self.page.click(self.TAB_CLIENTS)
        expect(self.page.locator(self.TAB_CONTENT_CLIENTS)).to_be_visible()
    
    def switch_to_connections_tab(self) -> None:
        """Switch to Connections tab."""
        self.page.click(self.TAB_CONNECTIONS)
        expect(self.page.locator(self.TAB_CONTENT_CONNECTIONS)).to_be_visible()
    
    def is_clients_tab_active(self) -> bool:
        """Check if Download Clients tab is active."""
        return "active" in self.page.locator(self.TAB_CLIENTS).get_attribute("class")
    
    def is_connections_tab_active(self) -> bool:
        """Check if Connections tab is active."""
        return "active" in self.page.locator(self.TAB_CONNECTIONS).get_attribute("class")
    
    # ========== Client Operations ==========
    
    def wait_for_clients_loaded(self, timeout: int = 10000) -> None:
        """Wait for clients list to load."""
        self.page.wait_for_selector(
            self.LOADING_CLIENTS, 
            state="hidden", 
            timeout=timeout
        )
    
    def get_client_cards(self):
        """Get all client cards."""
        return self.page.locator(self.CLIENT_CARD).all()
    
    def get_client_card_count(self) -> int:
        """Get the number of client cards."""
        return self.page.locator(self.CLIENT_CARD).count()
    
    def get_client_by_name(self, name: str):
        """Get a specific client card by name.
        
        Args:
            name: Name of the client
            
        Returns:
            Locator for the client card
        """
        return self.page.locator(f"{self.CLIENT_CARD}:has-text('{name}')")
    
    def open_add_client_modal(self) -> None:
        """Open the add client modal."""
        self.page.click(self.ADD_CLIENT_BTN)
        expect(self.page.locator(self.CLIENT_MODAL)).to_be_visible()
    
    def close_client_modal(self) -> None:
        """Close the client modal."""
        self.page.click(f"{self.CLIENT_MODAL} [data-bs-dismiss='modal']")
        expect(self.page.locator(self.CLIENT_MODAL)).not_to_be_visible()
    
    def fill_client_form(
        self,
        name: str,
        host: str,
        port: int,
        password: str,
        username: str = "",
        client_type: str = "deluge",
        connection_type: str = "rpc"
    ):
        """Fill out the client form.
        
        Args:
            name: Client name
            host: Host address
            port: Port number
            password: Client password
            username: Username (optional, for RPC)
            client_type: Type of client (default: deluge)
            connection_type: Connection method (rpc or web)
        """
        self.page.fill(self.CLIENT_NAME_INPUT, name)
        
        # Set client type and connection type FIRST
        # because username field visibility depends on connection type
        self.page.select_option(self.CLIENT_TYPE_SELECT, client_type)
        self.page.select_option(self.CLIENT_CONNECTION_TYPE_SELECT, connection_type)
        
        # Wait for username field visibility to update based on connection type
        if connection_type == "rpc":
            expect(self.page.locator("#usernameField")).to_be_visible()
        
        self.page.fill(self.CLIENT_HOST_INPUT, host)
        self.page.fill(self.CLIENT_PORT_INPUT, str(port))
        if username and connection_type == "rpc":
            self.page.fill(self.CLIENT_USERNAME_INPUT, username)
        self.page.fill(self.CLIENT_PASSWORD_INPUT, password)
    
    def save_client(self) -> None:
        """Click save client button."""
        self.page.click(self.SAVE_CLIENT_BTN)
    
    def test_client_connection(self) -> None:
        """Click test connection button."""
        self.page.click(self.TEST_CONNECTION_BTN)
    
    def edit_client(self, client_name: str) -> None:
        """Click edit button on a client card.
        
        Args:
            client_name: Name of the client to edit
        """
        card = self.get_client_by_name(client_name)
        # Edit button is btn-primary with fa-edit icon
        card.locator(".btn-primary:has(.fa-edit)").click()
        expect(self.page.locator(self.CLIENT_MODAL)).to_be_visible()
    
    def delete_client(self, client_name: str) -> None:
        """Click delete button on a client card and confirm.
        
        Args:
            client_name: Name of the client to delete
        """
        card = self.get_client_by_name(client_name)
        card.locator(".btn-danger").click()
        expect(self.page.locator(self.DELETE_MODAL)).to_be_visible()
        self.page.click(self.CONFIRM_DELETE_BTN)
    
    def close_delete_modal(self) -> None:
        """Close the delete confirmation modal without confirming."""
        self.page.click(f"{self.DELETE_MODAL} [data-bs-dismiss='modal']")
        expect(self.page.locator(self.DELETE_MODAL)).not_to_be_visible()
    
    # ========== Connection Operations ==========
    
    def wait_for_connections_loaded(self, timeout: int = 10000) -> None:
        """Wait for connections list to load."""
        self.page.wait_for_selector(
            self.LOADING_CONNECTIONS, 
            state="hidden", 
            timeout=timeout
        )
    
    def get_connection_cards(self):
        """Get all connection cards."""
        return self.page.locator(self.CONNECTION_CARD).all()
    
    def get_connection_card_count(self) -> int:
        """Get the number of connection cards."""
        return self.page.locator(self.CONNECTION_CARD).count()
    
    def open_add_connection_modal(self) -> None:
        """Open the add connection modal."""
        self.page.click(self.ADD_CONNECTION_BTN)
        expect(self.page.locator(self.CONNECTION_MODAL)).to_be_visible()
    
    def close_connection_modal(self) -> None:
        """Close the connection modal."""
        self.page.click(f"{self.CONNECTION_MODAL} [data-bs-dismiss='modal']")
        expect(self.page.locator(self.CONNECTION_MODAL)).not_to_be_visible()
    
    def fill_connection_form(
        self,
        from_client: str,
        to_client: str,
        from_type: str = "sftp",
        to_type: str = "sftp",
        from_sftp_host: str = "",
        from_sftp_port: int = 22,
        from_sftp_username: str = "",
        from_sftp_password: str = "",
        to_sftp_host: str = "",
        to_sftp_port: int = 22,
        to_sftp_username: str = "",
        to_sftp_password: str = "",
    ):
        """Fill out the connection form.
        
        Args:
            from_client: Source client name
            to_client: Destination client name
            from_type: Transfer type for source (sftp or local)
            to_type: Transfer type for destination (sftp or local)
            from_sftp_*: SFTP config for source
            to_sftp_*: SFTP config for destination
        """
        # Select clients
        self.page.select_option(self.CONNECTION_FROM_SELECT, from_client)
        self.page.select_option(self.CONNECTION_TO_SELECT, to_client)
        
        # Select transfer types
        self.page.select_option(self.CONNECTION_FROM_TYPE, from_type)
        self.page.select_option(self.CONNECTION_TO_TYPE, to_type)
        
        # Fill SFTP config for source if SFTP
        if from_type == "sftp":
            if from_sftp_host:
                self.page.fill(self.FROM_SFTP_HOST, from_sftp_host)
            self.page.fill(self.FROM_SFTP_PORT, str(from_sftp_port))
            if from_sftp_username:
                self.page.fill(self.FROM_SFTP_USERNAME, from_sftp_username)
            if from_sftp_password:
                self.page.fill(self.FROM_SFTP_PASSWORD, from_sftp_password)
        
        # Fill SFTP config for destination if SFTP
        if to_type == "sftp":
            if to_sftp_host:
                self.page.fill(self.TO_SFTP_HOST, to_sftp_host)
            self.page.fill(self.TO_SFTP_PORT, str(to_sftp_port))
            if to_sftp_username:
                self.page.fill(self.TO_SFTP_USERNAME, to_sftp_username)
            if to_sftp_password:
                self.page.fill(self.TO_SFTP_PASSWORD, to_sftp_password)
    
    def fill_connection_paths(
        self,
        source_dot_torrent_path: str,
        source_download_path: str,
        dest_tmp_path: str,
        dest_download_path: str,
    ):
        """Fill the path configuration fields.
        
        Note: These fields are disabled until connection test succeeds.
        """
        self.page.fill(self.SOURCE_DOT_TORRENT_PATH, source_dot_torrent_path)
        self.page.fill(self.SOURCE_DOWNLOAD_PATH, source_download_path)
        self.page.fill(self.DEST_TMP_PATH, dest_tmp_path)
        self.page.fill(self.DEST_DOWNLOAD_PATH, dest_download_path)
    
    def test_connection(self) -> None:
        """Click the test connection button (for connections modal)."""
        self.page.click(self.TEST_CONNECTION_BTN2)
    
    def save_connection(self) -> None:
        """Click save connection button."""
        self.page.click(self.SAVE_CONNECTION_BTN)
    
    def get_connection_by_clients(self, from_client: str, to_client: str):
        """Get a connection card by client names.
        
        Args:
            from_client: Source client name
            to_client: Destination client name
            
        Returns:
            Locator for the connection card
        """
        return self.page.locator(
            f"{self.CONNECTION_CARD}:has-text('{from_client}'):has-text('{to_client}')"
        )
    
    def delete_connection(self, from_client: str, to_client: str) -> None:
        """Click delete on a connection and confirm.
        
        Note: Connections use browser confirm() dialog, not Bootstrap modal.
        We use once() to set up a one-time dialog handler.
        
        Args:
            from_client: Source client name
            to_client: Destination client name
        """
        card = self.get_connection_by_clients(from_client, to_client)
        
        # Set up one-time dialog handler to accept the confirmation
        # Using once() prevents handler leak
        self.page.once("dialog", lambda dialog: dialog.accept())
        
        # Click delete
        card.locator(".btn-danger").click()
    
    def edit_connection(self, from_client: str, to_client: str) -> None:
        """Click edit on a connection.
        
        Args:
            from_client: Source client name
            to_client: Destination client name
        """
        card = self.get_connection_by_clients(from_client, to_client)
        card.locator(".btn-primary").click()
        expect(self.page.locator(self.CONNECTION_MODAL)).to_be_visible()
    
    # ========== Helper Methods for Tests ==========
    
    def get_clients_tab(self):
        """Get the clients tab locator."""
        return self.page.locator(self.TAB_CLIENTS)
    
    def get_connections_tab(self):
        """Get the connections tab locator."""
        return self.page.locator(self.TAB_CONNECTIONS)
    
    def get_client_count(self) -> int:
        """Get the number of clients (alias for get_client_card_count)."""
        return self.get_client_card_count()
    
    def get_client_names(self) -> list[str]:
        """Get the names of all clients.
        
        Returns:
            List of client names
        """
        cards = self.get_client_cards()
        names = []
        for card in cards:
            # Client name is in the card header
            header = card.locator(".card-header")
            if header.count() > 0:
                names.append(header.text_content().strip())
        return names
    
    def get_connection_count(self) -> int:
        """Get the number of connections (alias for get_connection_card_count)."""
        return self.get_connection_card_count()
