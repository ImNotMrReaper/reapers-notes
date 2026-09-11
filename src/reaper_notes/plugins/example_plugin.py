"""
example_plugin.py: Reference implementation demonstrating custom plugin development for Reaper's Notes.
Adds Document Statistics, Timestamp Insertion, and Text Transformation tools.
"""

from datetime import datetime
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
from .base import NotesPlugin


class ExampleToolsPlugin(NotesPlugin):
    id = "example_tools"
    name = "Editor Utilities & Statistics"
    description = "Provides word count, line count, character statistics, and timestamp insertion."
    version = "1.0.0"
    author = "Mr. Reaper"

    def on_load(self, window):
        pass

    def on_unload(self, window):
        pass

    def get_menu_items(self, window):
        return [
            ("Document Statistics...", lambda: self.show_statistics(window)),
            ("Insert Date & Timestamp", lambda: self.insert_timestamp(window)),
            ("Convert Selection to Title Case", lambda: self.transform_title_case(window)),
        ]

    def show_statistics(self, window):
        page = window.get_current_page()
        if not page:
            window.set_status_message("⚠️ No active document open.")
            return

        text = page.get_full_text()
        char_count = len(text)
        word_count = len(text.split()) if text else 0
        line_count = len(text.splitlines()) if text else 0

        dialog = Adw.MessageDialog(
            transient_for=window,
            heading="Document Statistics",
            body=(
                f"• Lines: {line_count:,}\n"
                f"• Words: {word_count:,}\n"
                f"• Characters (with spaces): {char_count:,}\n"
                f"• Characters (no spaces): {len(text.replace(' ', '').replace('\\n', '')):,}"
            ),
        )
        dialog.add_response("ok", "Close")
        dialog.set_default_response("ok")
        dialog.present()

    def insert_timestamp(self, window):
        page = window.get_current_page()
        if not page:
            return

        now_str = datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
        it = page.buffer.get_iter_at_mark(page.buffer.get_insert())
        page.buffer.insert(it, now_str)
        window.set_status_message("🕒 Timestamp inserted.")

    def transform_title_case(self, window):
        page = window.get_current_page()
        if not page:
            return

        bounds = page.buffer.get_selection_bounds()
        if bounds:
            start, end = bounds
            sel_text = page.buffer.get_text(start, end, True)
            if sel_text:
                page.buffer.delete(start, end)
                page.buffer.insert(start, sel_text.title())
                window.set_status_message("✨ Selection converted to Title Case.")
        else:
            window.set_status_message("⚠️ Select text first to convert to Title Case.")
