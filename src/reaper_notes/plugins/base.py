"""
base.py: Base Plugin Interface for Reaper's Notes.
"""

from typing import Callable, List, Tuple, Any


class NotesPlugin:
    """Base class for all Reaper's Notes extensions and plugins."""
    id: str = "base_plugin"
    name: str = "Unnamed Plugin"
    description: str = ""
    version: str = "1.0.0"
    author: str = "Community"
    enabled: bool = True

    def on_load(self, window: Any) -> None:
        """Invoked when the plugin is activated and attached to the main window."""
        pass

    def on_unload(self, window: Any) -> None:
        """Invoked when the plugin is deactivated or detached."""
        pass

    def get_menu_items(self, window: Any) -> List[Tuple[str, Callable[[], None]]]:
        """
        Return a list of (label, callback) tuples to register in the Plugins menu.
        Example: [("Word & Char Count", self.show_stats)]
        """
        return []
