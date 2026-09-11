"""
obsidian_plugin.py: Obsidian Vault Synchronization Plugin for Reaper's Notes.
Allows instant pushing of notes to Obsidian vaults and creates Obsidian notes with YAML frontmatter.
"""

from typing import Any
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from .base import NotesPlugin
try:
    from ..obsidian import discover_vaults, get_default_vault, push_to_obsidian, create_obsidian_template
except (ImportError, ValueError):
    from obsidian import discover_vaults, get_default_vault, push_to_obsidian, create_obsidian_template


class ObsidianPlugin(NotesPlugin):
    id = "obsidian_sync"
    name = "Obsidian Vault Sync"
    description = "Seamlessly push documents into Obsidian vaults and create frontmatter-formatted notes."
    version = "1.0.0"
    author = "Mr. Reaper"

    def __init__(self):
        super().__init__()
        self.window = None

    def on_load(self, window: Any):
        self.window = window

    def on_unload(self, window: Any):
        self.window = None

    def get_menu_items(self, window: Any):
        return [
            ("Push Note to Obsidian Vault (Ctrl+Alt+O)", lambda: self.push_note(window)),
            ("New Obsidian Note (Ctrl+Shift+O)", lambda: self.new_obsidian_note(window)),
        ]

    def push_note(self, window: Any):
        """Pushes current document content to the default Obsidian vault."""
        page = window.get_current_page()
        if not page:
            window.set_status_message("⚠️ No active note to push.")
            return

        content = page.get_full_text()
        if not content.strip():
            window.set_status_message("⚠️ Note is empty. Nothing to push.")
            return

        title = page.title if page.title and page.title != "Untitled Note" else ""
        default_vault = get_default_vault()
        if not default_vault:
            self._prompt_vault_selection(window, content, title)
            return

        vault_name, vault_path = default_vault
        success, res = push_to_obsidian(content, title, vault_path)
        if success:
            window.set_status_message(f"🟣 Note pushed to Obsidian: {vault_name}/{res.split('/')[-1]}")
        else:
            window.set_status_message(f"❌ Failed to push note: {res}")

    def new_obsidian_note(self, window: Any):
        """Opens a new tab populated with Obsidian frontmatter."""
        dialog = Adw.MessageDialog(
            transient_for=window,
            heading="New Obsidian Note",
            body="Enter a title for your new Obsidian note:",
        )
        entry = Gtk.Entry()
        entry.set_placeholder_text("e.g. Project Architecture, Daily Scratchpad...")
        entry.set_margin_top(8)
        entry.set_margin_bottom(8)
        entry.set_margin_start(16)
        entry.set_margin_end(16)
        dialog.set_extra_child(entry)

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("create", "Create Note")
        dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("create")

        def on_response(dlg, response):
            if response == "create":
                note_title = entry.get_text().strip() or "Untitled Note"
                template = create_obsidian_template(note_title)
                page = window.create_new_page(title=note_title)
                page.buffer.set_text(template)
                page.set_language_by_id("markdown")
                window.set_status_message(f"🟣 Created new Obsidian note: '{note_title}'")

        dialog.connect("response", on_response)
        entry.connect("activate", lambda _: dialog.response("create"))
        dialog.present()

    def _prompt_vault_selection(self, window: Any, content: str, title: str):
        vaults = discover_vaults()
        if not vaults:
            window.set_status_message("⚠️ No Obsidian vaults found in ~/.config/obsidian or ~/Documents.")
            return

        dialog = Adw.MessageDialog(
            transient_for=window,
            heading="Select Obsidian Vault",
            body="Choose destination vault:",
        )
        v_names = list(vaults.keys())
        dropdown = Gtk.DropDown.new_from_strings(v_names)
        dropdown.set_margin_start(16)
        dropdown.set_margin_end(16)
        dialog.set_extra_child(dropdown)

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("push", "Push Note")
        dialog.set_response_appearance("push", Adw.ResponseAppearance.SUGGESTED)

        def on_response(dlg, response):
            if response == "push":
                sel_name = v_names[dropdown.get_selected()]
                sel_path = vaults[sel_name]
                success, res = push_to_obsidian(content, title, sel_path)
                if success:
                    window.set_status_message(f"🟣 Note pushed to Obsidian vault '{sel_name}'!")
                else:
                    window.set_status_message(f"❌ Error: {res}")

        dialog.connect("response", on_response)
        dialog.present()
