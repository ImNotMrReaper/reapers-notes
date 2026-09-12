"""
obsidian_plugin.py: Obsidian Vault Synchronization Plugin for Reaper's Notes.
Allows instant pushing of notes to Obsidian vaults, discovery of vaults created
by Obsidian, folder selection via file manager, and template generation with YAML frontmatter.
"""

import os
from typing import Any
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
from gi.repository import Gtk, Adw, Gio

from .base import NotesPlugin
try:
    from ..obsidian import (
        discover_vaults,
        discover_vault_details,
        get_default_vault,
        set_active_vault_path,
        register_custom_vault,
        push_to_obsidian,
        create_obsidian_template,
    )
except (ImportError, ValueError):
    from obsidian import (
        discover_vaults,
        discover_vault_details,
        get_default_vault,
        set_active_vault_path,
        register_custom_vault,
        push_to_obsidian,
        create_obsidian_template,
    )


class ObsidianPlugin(NotesPlugin):
    id = "obsidian_sync"
    name = "Obsidian Vault Sync"
    description = "Seamlessly push documents into Obsidian vaults, auto-detect Obsidian-created folders, and select custom vaults via file manager."
    version = "1.2.0"
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
            ("Manage / Select Obsidian Vaults...", lambda: self.show_vault_manager_dialog(window)),
            ("Choose Vault Folder in File Manager...", lambda: self.select_vault_from_file_manager(window)),
        ]

    def push_note(self, window: Any):
        """Pushes current document content to the active Obsidian vault."""
        if hasattr(window, "trigger_action_progress"):
            window.trigger_action_progress(600)

        page = window.get_current_page()
        if not page:
            window.set_status_message("⚠️ No active note to push.")
            return

        content = page.get_full_text()
        title = page.title if page.title and page.title != "Untitled Note" else ""
        if not content.strip():
            note_title = title or "Untitled Note"
            content = create_obsidian_template(note_title)
            page.buffer.set_text(content)

        default_vault = get_default_vault()
        if not default_vault:
            # Prompt user to choose or pick via file manager
            self._prompt_vault_selection(window, content, title)
            return

        vault_name, vault_path = default_vault
        success, res = push_to_obsidian(content, title, vault_path)
        if success:
            window.set_status_message(f"🟣 Note pushed to Obsidian: {vault_name}/{os.path.basename(res)}")
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
                page = window.open_new_tab()
                page.buffer.set_text(template)
                page.set_language_by_id("markdown")
                window.set_status_message(f"🟣 Created new Obsidian note: '{note_title}'")
            dlg.close()

        dialog.connect("response", on_response)
        entry.connect("activate", lambda _: dialog.response("create"))
        dialog.present()

    def select_vault_from_file_manager(self, window: Any, on_success=None):
        """Opens native file manager chooser to select any folder as an Obsidian vault."""
        if hasattr(Gtk, "FileDialog"):
            file_dialog = Gtk.FileDialog.new()
            file_dialog.set_title("Select Obsidian Vault Folder")

            def on_folder_chosen(dialog, result):
                try:
                    gfile = dialog.select_folder_finish(result)
                    if gfile:
                        folder_path = gfile.get_path()
                        success, msg = register_custom_vault(folder_path)
                        if success:
                            window.set_status_message(f"🟣 {msg}")
                            if on_success:
                                on_success(folder_path)
                        else:
                            window.set_status_message(f"❌ {msg}")
                except Exception as e:
                    # User cancelled or dialog dismissed
                    pass

            file_dialog.select_folder(window, None, on_folder_chosen)
        else:
            native = Gtk.FileChooserNative.new(
                "Select Obsidian Vault Folder",
                window,
                Gtk.FileChooserAction.SELECT_FOLDER,
                "Select Vault",
                "Cancel",
            )

            def on_native_response(dialog, response_id):
                if response_id == Gtk.ResponseType.ACCEPT:
                    gfile = dialog.get_file()
                    if gfile:
                        folder_path = gfile.get_path()
                        success, msg = register_custom_vault(folder_path)
                        if success:
                            window.set_status_message(f"🟣 {msg}")
                            if on_success:
                                on_success(folder_path)
                        else:
                            window.set_status_message(f"❌ {msg}")
                dialog.destroy()

            native.connect("response", on_native_response)
            native.show()

    def show_vault_manager_dialog(self, window: Any):
        """Displays detected Obsidian-created vaults and allows selection or browsing via file manager."""
        dialog = Adw.MessageDialog(
            transient_for=window,
            heading="Obsidian Vault Manager",
            body="Select the active vault or browse your file manager to add a folder:",
        )
        dialog.set_default_size(480, 360)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        main_box.set_margin_start(16)
        main_box.set_margin_end(16)
        main_box.set_margin_top(8)
        main_box.set_margin_bottom(8)

        # Scrolled list of detected vaults
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_min_content_height(180)
        scrolled.set_vexpand(True)

        listbox = Gtk.ListBox()
        listbox.add_css_class("boxed-list")
        scrolled.set_child(listbox)
        main_box.append(scrolled)

        vault_details = discover_vault_details()
        row_widgets = []

        for v in vault_details:
            row = Adw.ActionRow()
            row.set_title(v["name"])
            
            # Subtitle indicating detection source and directory
            marker_badge = " [Obsidian-created]" if v["has_obsidian_dir"] else ""
            row.set_subtitle(f"{v['source']}{marker_badge} • {v['path']}")

            check = Gtk.CheckButton()
            check.set_active(v["is_active"])
            check.connect("toggled", lambda cb, path=v["path"]: self._on_vault_toggled(cb, path, window, dialog))
            row.add_prefix(check)
            row.set_activatable_widget(check)

            listbox.append(row)
            row_widgets.append((row, check, v["path"]))

        if not vault_details:
            empty_lbl = Gtk.Label(label="No Obsidian vaults auto-detected yet.\nClick 'Browse in File Manager' below to select a folder.")
            empty_lbl.set_justify(Gtk.Justification.CENTER)
            empty_lbl.add_css_class("dim-label")
            empty_lbl.set_margin_top(24)
            empty_lbl.set_margin_bottom(24)
            main_box.append(empty_lbl)

        # Browse button
        browse_btn = Gtk.Button(label="📁 Browse in File Manager...")
        browse_btn.add_css_class("pill")
        browse_btn.set_halign(Gtk.Align.CENTER)
        browse_btn.connect("clicked", lambda _: self._browse_and_refresh(window, dialog))
        main_box.append(browse_btn)

        dialog.set_extra_child(main_box)
        dialog.add_response("close", "Close")
        dialog.set_default_response("close")
        dialog.present()

    def _on_vault_toggled(self, check_btn: Gtk.CheckButton, path: str, window: Any, dialog: Any):
        if check_btn.get_active():
            set_active_vault_path(path)
            v_name = os.path.basename(path)
            window.set_status_message(f"🟣 Active Obsidian vault set to: '{v_name}'")
            dialog.response("close")

    def _browse_and_refresh(self, window: Any, parent_dialog: Any):
        def on_selected(path):
            parent_dialog.response("close")
            self.show_vault_manager_dialog(window)

        self.select_vault_from_file_manager(window, on_success=on_selected)

    def _prompt_vault_selection(self, window: Any, content: str, title: str):
        vault_details = discover_vault_details()
        if not vault_details:
            # Let user choose via file manager
            def on_picked(path):
                v_name = os.path.basename(path)
                success, res = push_to_obsidian(content, title, path)
                if success:
                    window.set_status_message(f"🟣 Note pushed to Obsidian vault '{v_name}'!")
                else:
                    window.set_status_message(f"❌ Error: {res}")

            self.select_vault_from_file_manager(window, on_success=on_picked)
            return

        dialog = Adw.MessageDialog(
            transient_for=window,
            heading="Select Destination Obsidian Vault",
            body="Choose destination vault or browse file manager:",
        )
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        
        v_names = [v["name"] for v in vault_details]
        dropdown = Gtk.DropDown.new_from_strings(v_names)
        dropdown.set_margin_start(16)
        dropdown.set_margin_end(16)
        box.append(dropdown)

        browse_btn = Gtk.Button(label="📁 Browse in File Manager...")
        browse_btn.set_halign(Gtk.Align.CENTER)
        box.append(browse_btn)

        dialog.set_extra_child(box)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("push", "Push Note")
        dialog.set_response_appearance("push", Adw.ResponseAppearance.SUGGESTED)

        def on_browse_clicked(_):
            dialog.response("cancel")
            def on_custom_picked(path):
                v_name = os.path.basename(path)
                success, res = push_to_obsidian(content, title, path)
                if success:
                    window.set_status_message(f"🟣 Note pushed to Obsidian vault '{v_name}'!")
                else:
                    window.set_status_message(f"❌ Error: {res}")
            self.select_vault_from_file_manager(window, on_success=on_custom_picked)

        browse_btn.connect("clicked", on_browse_clicked)

        def on_response(dlg, response):
            if response == "push":
                sel_idx = dropdown.get_selected()
                sel_vault = vault_details[sel_idx]
                set_active_vault_path(sel_vault["path"])
                success, res = push_to_obsidian(content, title, sel_vault["path"])
                if success:
                    window.set_status_message(f"🟣 Note pushed to Obsidian vault '{sel_vault['name']}'!")
                else:
                    window.set_status_message(f"❌ Error: {res}")

        dialog.connect("response", on_response)
        dialog.present()
