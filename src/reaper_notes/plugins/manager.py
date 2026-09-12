"""
manager.py: Plugin Manager and Lifecycle Controller for Reaper's Notes.
Handles discovery, loading, settings persistence, and UI dialogs for extensions.
"""

import os
import sys
import glob
import inspect
import importlib.util
from pathlib import Path
from typing import Dict, List, Any
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
from gi.repository import Gtk, Adw, Gio, GLib

from .base import NotesPlugin
from .example_plugin import ExampleToolsPlugin
from .ai_plugin import AIAssistantPlugin
from .obsidian_plugin import ObsidianPlugin
from .ascii_plugin import AsciiArtPlugin
try:
    from ..settings import get_setting, set_setting
except (ImportError, ValueError):
    from settings import get_setting, set_setting

USER_PLUGINS_DIR = Path.home() / ".config" / "reaper-notes" / "plugins"


class PluginManager:
    """Orchestrates plugin registration, lifecycle, and dynamic menu binding."""

    def __init__(self, window: Any):
        self.window = window
        self.plugins: Dict[str, NotesPlugin] = {}
        self.user_plugins_dir = USER_PLUGINS_DIR
        self.user_plugins_dir.mkdir(parents=True, exist_ok=True)

        self._register_builtins()
        self._discover_user_plugins()
        self._activate_enabled_plugins()

    def _register_builtins(self):
        builtins = [
            AIAssistantPlugin(),
            ObsidianPlugin(),
            AsciiArtPlugin(),
            ExampleToolsPlugin(),
        ]
        for p in builtins:
            self.plugins[p.id] = p

    def _discover_user_plugins(self):
        """Scans ~/.config/reaper-notes/plugins for external Python plugin files."""
        builtin_module_names = {"base", "manager", "obsidian_plugin", "ai_plugin", "ascii_plugin", "example_plugin"}
        for py_path in glob.glob(str(self.user_plugins_dir / "*.py")):
            mod_name = Path(py_path).stem
            if mod_name.startswith("__") or mod_name in builtin_module_names:
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"user_plugin_{mod_name}", py_path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    for _, cls in inspect.getmembers(mod, inspect.isclass):
                        if issubclass(cls, NotesPlugin) and cls is not NotesPlugin:
                            instance = cls()
                            self.plugins[instance.id] = instance
            except Exception as e:
                print(f"[PluginManager] Failed to load user plugin {py_path}: {e}", file=sys.stderr)

    def _activate_enabled_plugins(self):
        disabled = set(get_setting("disabled_plugins", []))
        for p_id, plugin in self.plugins.items():
            if p_id not in disabled:
                plugin.enabled = True
                try:
                    plugin.on_load(self.window)
                except Exception as e:
                    print(f"[PluginManager] Error loading plugin '{p_id}': {e}", file=sys.stderr)
            else:
                plugin.enabled = False

    def is_plugin_enabled(self, p_id: str) -> bool:
        return self.plugins.get(p_id, None) is not None and self.plugins[p_id].enabled

    def get_plugin(self, p_id: str) -> Any:
        return self.plugins.get(p_id, None)

    def toggle_plugin(self, p_id: str, enable: bool):
        plugin = self.plugins.get(p_id)
        if not plugin:
            return

        disabled = set(get_setting("disabled_plugins", []))
        if enable:
            disabled.discard(p_id)
            plugin.enabled = True
            try:
                plugin.on_load(self.window)
            except Exception as e:
                print(f"[PluginManager] Error activating '{p_id}': {e}", file=sys.stderr)
        else:
            disabled.add(p_id)
            plugin.enabled = False
            try:
                plugin.on_unload(self.window)
            except Exception as e:
                print(f"[PluginManager] Error deactivating '{p_id}': {e}", file=sys.stderr)

        set_setting("disabled_plugins", list(disabled))

    def build_plugins_menu(self) -> Gio.Menu:
        """Constructs a dynamic Gio.Menu representing active plugin actions."""
        menu = Gio.Menu()

        for p_id, plugin in self.plugins.items():
            if not plugin.enabled:
                continue

            items = plugin.get_menu_items(self.window)
            if not items:
                continue

            section = Gio.Menu()
            for idx, (label, callback) in enumerate(items):
                action_name = f"plugin_{p_id}_{idx}"
                # Register action on window
                action = Gio.SimpleAction.new(action_name, None)
                action.connect("activate", lambda a, p, cb=callback: cb())
                self.window.add_action(action)
                section.append(label, f"win.{action_name}")

            menu.append_section(plugin.name, section)

        manage_section = Gio.Menu()
        manage_section.append("Manage Plugins...", "win.show_plugins_manager")
        manage_section.append("Open User Plugins Folder", "win.open_plugins_folder")
        menu.append_section(None, manage_section)

        return menu

    def show_manager_dialog(self):
        """Displays the Plugin Management preferences window."""
        dialog = Adw.MessageDialog(
            transient_for=self.window,
            heading="Installed Plugins",
            body="Enable or disable plugins and extensions for Reaper's Notes:",
        )
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)

        list_box = Gtk.ListBox()
        list_box.add_css_class("boxed-list")

        for p_id, plugin in sorted(self.plugins.items(), key=lambda x: x[1].name):
            row = Adw.ActionRow()
            row.set_title(plugin.name)
            row.set_subtitle(f"v{plugin.version} by {plugin.author} — {plugin.description}")

            switch = Gtk.Switch()
            switch.set_valign(Gtk.Align.CENTER)
            switch.set_active(plugin.enabled)
            switch.connect("notify::active", lambda s, _, pid=p_id: self.toggle_plugin(pid, s.get_active()))

            row.add_suffix(switch)
            list_box.append(row)

        box.append(list_box)
        dialog.set_extra_child(box)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.present()
