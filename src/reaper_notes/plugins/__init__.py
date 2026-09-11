"""
Plugins package for Reaper's Notes.
"""

from .base import NotesPlugin
from .manager import PluginManager

__all__ = ["NotesPlugin", "PluginManager"]
