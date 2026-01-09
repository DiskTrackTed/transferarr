"""Page Object Models for UI testing."""
from .base_page import BasePage
from .dashboard_page import DashboardPage
from .torrents_page import TorrentsPage
from .settings_page import SettingsPage

__all__ = ['BasePage', 'DashboardPage', 'TorrentsPage', 'SettingsPage']
