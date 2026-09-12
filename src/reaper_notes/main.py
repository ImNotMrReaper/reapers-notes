#!/usr/bin/env python3
"""
main.py: Reaper Notes & Text Editor
Universal GTK4 / Libadwaita / GtkSourceView 5 desktop editor:
1. Multi-document tabbed interface (Adw.TabView & Adw.TabBar)
2. In-editor Find & Replace bar (Ctrl+F, Ctrl+H) with match count & navigation
3. Universal syntax highlighting for all programming & markup languages
4. Terminal-grade inline ghost-text autocomplete (ble.sh / fish style)
5. Local Whisper voice-to-text dictation (Ctrl+Alt+V, sub-200ms CPU inference)
6. Antigravity AI task dispatch hook (Ctrl+Alt+A)
7. Tri-Factor Biometric Locked Notes (Howdy Face ID, Fingerprint, Password)
8. Zoom scaling (Ctrl++, Ctrl+-, Ctrl+0), Line numbers & Right margin guides
9. Unsaved changes protection dialog & Save As (Ctrl+Shift+S)
10. Pure OLED Pitch-Black (#000000) & Ubuntu Purple (#7764D8) theme alignment
"""

import os
import sys
import time
import shutil
from datetime import datetime
from pathlib import Path
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GtkSource, Adw, Gdk, GLib, Pango, Gio

from security import authenticate_biometric, encrypt_note, decrypt_note, is_locked_note, MAGIC_HEADER
from autocomplete import AutocompleteEngine
from voice import VoiceDictationManager
from ai_assistant import dispatch_antigravity_prompt
from settings import load_settings, save_settings, get_setting, set_setting
from obsidian import discover_vaults, get_default_vault, push_to_obsidian, create_obsidian_template
from plugins.manager import PluginManager, USER_PLUGINS_DIR

VAULT_DIR = Path.home() / "Documents" / "Valut"
DEFAULT_NOTES_DIR = Path.home() / "Documents" / "Notes"
LOCKED_NOTES_DIR = Path.home() / "Documents" / "Notes" / "Locked"
THEME_CSS_PATH = Path(__file__).parent / "theme.css"
DEFAULT_FONT_SIZE = 13


def ensure_locked_files_in_locked_dir():
    """
    Scans DEFAULT_NOTES_DIR for any locked note files (.locked extension or encrypted header)
    residing outside LOCKED_NOTES_DIR and automatically relocates them to LOCKED_NOTES_DIR.
    """
    try:
        LOCKED_NOTES_DIR.mkdir(parents=True, exist_ok=True)
        if not DEFAULT_NOTES_DIR.exists():
            return
        for item in DEFAULT_NOTES_DIR.iterdir():
            if item.is_file() and item.parent.resolve() != LOCKED_NOTES_DIR.resolve():
                should_move = False
                if item.name.endswith(".locked"):
                    should_move = True
                else:
                    try:
                        with open(item, "rb") as f:
                            header = f.read(len(MAGIC_HEADER))
                            if header == MAGIC_HEADER:
                                should_move = True
                    except Exception:
                        pass
                if should_move:
                    target_name = item.name if item.name.endswith(".locked") else f"{item.stem}.locked"
                    target = LOCKED_NOTES_DIR / target_name
                    counter = 1
                    stem = Path(target_name).stem
                    while target.exists() and target.resolve() != item.resolve():
                        target = LOCKED_NOTES_DIR / f"{stem}_{counter}.locked"
                        counter += 1
                    shutil.move(str(item), str(target))
                    print(f"[reaper-notes] Relocated misplaced locked file to Locked folder: {target.name}", file=sys.stderr)
    except Exception as e:
        print(f"[reaper-notes] Error checking locked notes directory: {e}", file=sys.stderr)


def ensure_page_locked_storage(page) -> str:
    """
    Ensures that a locked page's underlying file is located inside LOCKED_NOTES_DIR
    with a .locked extension. If an existing file exists outside LOCKED_NOTES_DIR,
    it cleans up the old unencrypted/misplaced file. Returns the new canonical filepath.
    """
    LOCKED_NOTES_DIR.mkdir(parents=True, exist_ok=True)
    if not page.filepath:
        return ""

    old_path = Path(page.filepath)
    if old_path.parent.resolve() == LOCKED_NOTES_DIR.resolve() and old_path.name.endswith(".locked"):
        return str(old_path)

    stem = old_path.stem if not old_path.name.endswith(".locked") else old_path.stem
    filename = f"{stem}.locked"
    candidate = LOCKED_NOTES_DIR / filename
    counter = 1
    while candidate.exists() and candidate.resolve() != old_path.resolve():
        candidate = LOCKED_NOTES_DIR / f"{stem}_{counter}.locked"
        counter += 1

    if old_path.exists() and old_path.resolve() != candidate.resolve():
        try:
            old_path.unlink()
        except Exception:
            pass

    page.filepath = str(candidate)
    return str(candidate)


def ensure_page_unlocked_storage(page) -> str:
    """
    Ensures that an unlocked page's underlying file is moved out of LOCKED_NOTES_DIR
    into DEFAULT_NOTES_DIR (or retains its original parent if outside LOCKED_NOTES_DIR)
    with a standard plaintext extension.
    """
    DEFAULT_NOTES_DIR.mkdir(parents=True, exist_ok=True)
    if not page.filepath:
        return ""

    old_path = Path(page.filepath)
    if old_path.name.endswith(".locked"):
        stem = old_path.stem
        if not any(stem.endswith(ext) for ext in [".txt", ".md", ".py", ".sh", ".c", ".rs", ".json"]):
            filename = f"{stem}.txt"
        else:
            filename = stem
    else:
        filename = old_path.name

    if old_path.parent.resolve() == LOCKED_NOTES_DIR.resolve():
        target_dir = DEFAULT_NOTES_DIR
    else:
        target_dir = old_path.parent

    target_dir.mkdir(parents=True, exist_ok=True)
    candidate = target_dir / filename
    counter = 1
    stem_name = Path(filename).stem
    suffix = Path(filename).suffix
    while candidate.exists() and candidate.resolve() != old_path.resolve():
        candidate = target_dir / f"{stem_name}_{counter}{suffix}"
        counter += 1

    if old_path.exists() and old_path.resolve() != candidate.resolve():
        try:
            old_path.unlink()
        except Exception:
            pass

    page.filepath = str(candidate)
    return str(candidate)


class EditorPage(Gtk.Box):
    """Represents a single tab document in the editor."""

    @property
    def title(self) -> str:
        return self.get_title()

    def __init__(self, window, filepath=None, create_locked=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.filepath = filepath
        self.is_locked = create_locked
        self.is_modified = False
        self.active_ghost_text = ""
        self._suppress_autocomplete = False
        self.font_size_pt = DEFAULT_FONT_SIZE
        self.voice_start_mark = None
        self.voice_end_mark = None
        self.is_voice_dictating = False
        self._autosave_source_id = None

        self.lm = GtkSource.LanguageManager.get_default()
        self.sm = GtkSource.StyleSchemeManager.get_default()

        self._build_ui()
        self._setup_search()
        self._connect_signals()

        if filepath:
            self.load_file(filepath)
        elif create_locked:
            self._init_new_locked()
        else:
            default_lang = get_setting("default_language", "markdown")
            self.set_language_by_id(default_lang)

    def _build_ui(self):
        # 1. In-Editor Search & Replace Bar (collapsible)
        self.search_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.search_box.add_css_class("search-bar")
        self.search_box.set_visible(False)
        self.append(self.search_box)

        # Search Row
        row_find = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_icon = Gtk.Image.new_from_icon_name("system-search-symbolic")
        row_find.append(lbl_icon)

        self.entry_find = Gtk.SearchEntry()
        self.entry_find.set_hexpand(True)
        self.entry_find.set_placeholder_text("Find in document... (Enter = Next, Shift+Enter = Prev)")
        self.entry_find.connect("search-changed", self._on_search_text_changed)
        self.entry_find.connect("activate", lambda _: self.find_next())
        row_find.append(self.entry_find)

        self.lbl_matches = Gtk.Label(label="")
        self.lbl_matches.add_css_class("dim-label")
        row_find.append(self.lbl_matches)

        self.btn_prev = Gtk.Button.new_from_icon_name("go-up-symbolic")
        self.btn_prev.set_tooltip_text("Previous Match (Shift+Enter)")
        self.btn_prev.connect("clicked", lambda _: self.find_prev())
        row_find.append(self.btn_prev)

        self.btn_next = Gtk.Button.new_from_icon_name("go-down-symbolic")
        self.btn_next.set_tooltip_text("Next Match (Enter)")
        self.btn_next.connect("clicked", lambda _: self.find_next())
        row_find.append(self.btn_next)

        self.toggle_case = Gtk.ToggleButton(label="Aa")
        self.toggle_case.set_tooltip_text("Match Case")
        self.toggle_case.connect("toggled", self._on_search_settings_changed)
        row_find.append(self.toggle_case)

        self.toggle_word = Gtk.ToggleButton(label="\b")
        self.toggle_word.set_tooltip_text("Match Whole Word")
        self.toggle_word.connect("toggled", self._on_search_settings_changed)
        row_find.append(self.toggle_word)

        btn_close_search = Gtk.Button.new_from_icon_name("window-close-symbolic")
        btn_close_search.set_tooltip_text("Close Search (Esc)")
        btn_close_search.connect("clicked", lambda _: self.hide_search())
        row_find.append(btn_close_search)

        self.search_box.append(row_find)

        # Replace Row
        self.row_replace = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.row_replace.set_visible(False)
        lbl_rep_icon = Gtk.Image.new_from_icon_name("edit-find-replace-symbolic")
        self.row_replace.append(lbl_rep_icon)

        self.entry_replace = Gtk.Entry()
        self.entry_replace.set_hexpand(True)
        self.entry_replace.set_placeholder_text("Replace with...")
        self.row_replace.append(self.entry_replace)

        btn_rep = Gtk.Button(label="Replace")
        btn_rep.connect("clicked", lambda _: self.replace_current())
        self.row_replace.append(btn_rep)

        btn_rep_all = Gtk.Button(label="Replace All")
        btn_rep_all.connect("clicked", lambda _: self.replace_all())
        self.row_replace.append(btn_rep_all)

        self.search_box.append(self.row_replace)

        # 2. Text Editor using GtkSourceView 5
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.add_css_class("notes-scroll")
        self.scroll.set_vexpand(True)
        self.scroll.set_hexpand(True)
        self.append(self.scroll)

        self.buffer = GtkSource.Buffer()
        self.update_theme_scheme()

        self.editor = GtkSource.View.new_with_buffer(self.buffer)
        self.editor.add_css_class("notes-editor")
        self.editor.set_wrap_mode(Gtk.WrapMode.WORD_CHAR if get_setting("word_wrap", True) else Gtk.WrapMode.NONE)
        self.editor.set_monospace(True)
        self.editor.set_show_line_numbers(get_setting("line_numbers", False))
        self.editor.set_highlight_current_line(get_setting("highlight_current_line", False))
        self.editor.set_show_right_margin(get_setting("right_margin", False))
        self.editor.set_right_margin_position(80)
        self.editor.set_left_margin(20)
        self.editor.set_right_margin(20)
        self.editor.set_top_margin(14)
        self.editor.set_bottom_margin(14)
        self.scroll.set_child(self.editor)

        # Ghost text style tag
        self.ghost_tag = self.buffer.create_tag(
            "ghost_suggestion",
            foreground="#5c5770",
            style=Pango.Style.ITALIC
        )

    def _setup_search(self):
        self.search_settings = GtkSource.SearchSettings()
        self.search_settings.set_wrap_around(True)
        self.search_context = GtkSource.SearchContext.new(self.buffer, self.search_settings)
        self.search_context.set_highlight(True)
        self.search_context.connect("notify::occurrences-count", self._on_occurrences_count_changed)

    def _connect_signals(self):
        self.buffer.connect("changed", self._on_buffer_changed)
        self.buffer.connect("notify::cursor-position", self._on_cursor_position_changed)

    def _on_cursor_position_changed(self, *args):
        self.window.update_status_bar()

    def _on_occurrences_count_changed(self, context, param):
        count = context.get_occurrences_count()
        if count >= 0:
            self.lbl_matches.set_text(f"{count} matches" if count != 1 else "1 match")
        else:
            self.lbl_matches.set_text("")

    def _on_search_text_changed(self, entry):
        text = entry.get_text()
        self.search_settings.set_search_text(text if text else "")

    def _on_search_settings_changed(self, btn):
        self.search_settings.set_case_sensitive(self.toggle_case.get_active())
        self.search_settings.set_at_word_boundaries(self.toggle_word.get_active())

    def show_search(self, show_replace=False):
        self.search_box.set_visible(True)
        self.row_replace.set_visible(show_replace)
        if show_replace:
            self.entry_replace.grab_focus()
        else:
            self.entry_find.grab_focus()

    def hide_search(self):
        self.search_box.set_visible(False)
        self.search_settings.set_search_text("")
        self.editor.grab_focus()

    def find_next(self):
        insert_mark = self.buffer.get_insert()
        cursor_iter = self.buffer.get_iter_at_mark(insert_mark)
        found, start, end, wrapped = self.search_context.forward(cursor_iter)
        if found:
            self.buffer.select_range(start, end)
            self.editor.scroll_to_iter(start, 0.2, False, 0.0, 0.0)

    def find_prev(self):
        insert_mark = self.buffer.get_insert()
        cursor_iter = self.buffer.get_iter_at_mark(insert_mark)
        found, start, end, wrapped = self.search_context.backward(cursor_iter)
        if found:
            self.buffer.select_range(start, end)
            self.editor.scroll_to_iter(start, 0.2, False, 0.0, 0.0)

    def replace_current(self):
        bounds = self.buffer.get_selection_bounds()
        if bounds:
            rep_text = self.entry_replace.get_text()
            self.search_context.replace(bounds[0], bounds[1], rep_text, len(rep_text))
            self.find_next()

    def replace_all(self):
        rep_text = self.entry_replace.get_text()
        self.search_context.replace_all(rep_text, len(rep_text))

    def _init_new_locked(self):
        self.is_locked = True
        self.window.update_tab_title(self)

    def load_file(self, filepath: str):
        path = Path(filepath)
        if not path.exists():
            return

        with open(path, "rb") as f:
            raw_data = f.read()

        is_locked = is_locked_note(raw_data) or path.name.endswith(".locked")

        if is_locked:
            self.window.set_status_message("🔒 Locked note detected. Verifying biometric identity...")
            if not authenticate_biometric("unlock this encrypted note"):
                self.window.set_status_message("❌ Biometric authorization failed. Note remains locked.")
                return

            try:
                if is_locked_note(raw_data):
                    plaintext = decrypt_note(raw_data)
                else:
                    plaintext = raw_data.decode("utf-8", errors="replace")
                self.is_locked = True
            except Exception as e:
                self.window.set_status_message(f"❌ Decryption failed: {e}")
                return

            # Automatically ensure locked file is in the locked folder
            LOCKED_NOTES_DIR.mkdir(parents=True, exist_ok=True)
            if path.parent.resolve() != LOCKED_NOTES_DIR.resolve() or not path.name.endswith(".locked"):
                target_name = path.name if path.name.endswith(".locked") else f"{path.stem}.locked"
                target = LOCKED_NOTES_DIR / target_name
                counter = 1
                stem = Path(target_name).stem
                while target.exists() and target.resolve() != path.resolve():
                    target = LOCKED_NOTES_DIR / f"{stem}_{counter}.locked"
                    counter += 1
                try:
                    shutil.move(str(path), str(target))
                    path = target
                    self.window.set_status_message(f"🔒 Locked note relocated to Locked folder: {path.name}")
                except Exception as e:
                    print(f"Failed to move locked note to Locked folder: {e}", file=sys.stderr)
        else:
            self.is_locked = False
            plaintext = raw_data.decode("utf-8", errors="replace")

        self.filepath = str(path.resolve())
        self._detect_and_set_language(self.filepath)

        self._suppress_autocomplete = True
        try:
            self.buffer.set_text(plaintext)
            self.buffer.set_modified(False)
            self.is_modified = False
        finally:
            self._suppress_autocomplete = False

        self.window.update_tab_title(self)
        self.window.update_lock_button_state()
        if not is_locked:
            self.window.set_status_message(f"Loaded {path.name}")

    def _detect_and_set_language(self, filepath: str):
        lang = self.lm.guess_language(filepath, None)
        if not lang:
            # Check extension fallbacks
            ext = Path(filepath).suffix.lower()
            ext_map = {
                ".md": "markdown", ".markdown": "markdown",
                ".py": "python3", ".sh": "sh", ".bash": "sh",
                ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
                ".rs": "rust", ".go": "go", ".js": "javascript",
                ".ts": "typescript", ".html": "html", ".css": "css",
                ".json": "json", ".yaml": "yaml", ".yml": "yaml",
                ".xml": "xml", ".sql": "sql", ".ini": "ini",
                ".toml": "toml", ".dockerfile": "dockerfile"
            }
            if ext in ext_map:
                lang = self.lm.get_language(ext_map[ext])
        if lang:
            self.buffer.set_language(lang)

    def _on_buffer_changed(self, buffer):
        self.is_modified = True
        self.window.update_tab_title(self)
        self.window.update_status_bar()
        self._schedule_autosave()

        if self._suppress_autocomplete:
            return

        clean_text = self.get_clean_text()
        self.window.engine.update_document_words(clean_text)

        insert_mark = self.buffer.get_insert()
        cursor_iter = self.buffer.get_iter_at_mark(insert_mark)
        line_start = cursor_iter.copy()
        line_start.set_line_offset(0)
        line_text = self.buffer.get_text(line_start, cursor_iter, True)

        prefix = ""
        idx = len(line_text) - 1
        while idx >= 0 and (line_text[idx].isalnum() or line_text[idx] in "_-"):
            idx -= 1
        prefix = line_text[idx + 1:]

        if len(prefix) >= 2:
            suggestion = self.window.engine.get_suggestion(prefix)
            if suggestion:
                self.render_ghost_text(suggestion)
                return

        self.clear_ghost_text()

    def render_ghost_text(self, suggestion: str):
        if self.active_ghost_text == suggestion:
            return

        self.clear_ghost_text()

        insert_mark = self.buffer.get_insert()
        cursor_iter = self.buffer.get_iter_at_mark(insert_mark)

        self._suppress_autocomplete = True
        try:
            start_offset = cursor_iter.get_offset()
            self.buffer.insert(cursor_iter, suggestion)

            start_iter = self.buffer.get_iter_at_offset(start_offset)
            end_iter = self.buffer.get_iter_at_offset(start_offset + len(suggestion))
            self.buffer.apply_tag(self.ghost_tag, start_iter, end_iter)

            target_iter = self.buffer.get_iter_at_offset(start_offset)
            self.buffer.place_cursor(target_iter)

            self.active_ghost_text = suggestion
            self.window.lbl_suggestion.set_text(f"Tab: {suggestion}")
        finally:
            self._suppress_autocomplete = False

    def clear_ghost_text(self):
        if not self.active_ghost_text:
            return

        self._suppress_autocomplete = True
        try:
            start_iter = self.buffer.get_start_iter()
            end_iter = self.buffer.get_end_iter()
            self.buffer.remove_tag(self.ghost_tag, start_iter, end_iter)

            insert_mark = self.buffer.get_insert()
            cursor_iter = self.buffer.get_iter_at_mark(insert_mark)
            start_del = cursor_iter.copy()
            end_del = cursor_iter.copy()
            end_del.forward_chars(len(self.active_ghost_text))

            check_text = self.buffer.get_text(start_del, end_del, True)
            if check_text == self.active_ghost_text:
                self.buffer.delete(start_del, end_del)

            self.active_ghost_text = ""
            self.window.lbl_suggestion.set_text("")
        finally:
            self._suppress_autocomplete = False

    def commit_ghost_text(self):
        if not self.active_ghost_text:
            return

        self._suppress_autocomplete = True
        try:
            insert_mark = self.buffer.get_insert()
            cursor_iter = self.buffer.get_iter_at_mark(insert_mark)

            start_iter = cursor_iter.copy()
            end_iter = cursor_iter.copy()
            end_iter.forward_chars(len(self.active_ghost_text))

            self.buffer.remove_tag(self.ghost_tag, start_iter, end_iter)
            self.buffer.place_cursor(end_iter)

            self.active_ghost_text = ""
            self.window.lbl_suggestion.set_text("")
        finally:
            self._suppress_autocomplete = False

    def get_clean_text(self) -> str:
        start = self.buffer.get_start_iter()
        end = self.buffer.get_end_iter()
        full_text = self.buffer.get_text(start, end, True)

        if self.active_ghost_text:
            insert_mark = self.buffer.get_insert()
            cursor_iter = self.buffer.get_iter_at_mark(insert_mark)
            offset = cursor_iter.get_offset()
            ghost_len = len(self.active_ghost_text)

            before = full_text[:offset]
            after = full_text[offset + ghost_len:]
            return before + after

        return full_text

    def get_full_text(self) -> str:
        """Returns clean text buffer without active ghost suggestions."""
        return self.get_clean_text()

    def _schedule_autosave(self):
        """Debounces and schedules an automatic background save."""
        if hasattr(self, "_autosave_source_id") and self._autosave_source_id:
            GLib.source_remove(self._autosave_source_id)
            self._autosave_source_id = None

        if get_setting("auto_save", True):
            self._autosave_source_id = GLib.timeout_add(2500, self._on_autosave_timer)

    def _on_autosave_timer(self):
        self._autosave_source_id = None
        if self.is_modified and len(self.get_clean_text().strip()) > 0:
            if hasattr(self.window, "_save_page_immediately"):
                saved = self.window._save_page_immediately(self)
                if saved:
                    self.window.set_status_message(f"💾 Auto-saved: {self.get_title()}")
        return False

    @property
    def title(self) -> str:
        return self.get_title()

    @title.setter
    def title(self, value: str):
        self.default_title = value

    def get_title(self) -> str:
        if self.filepath:
            return Path(self.filepath).name
        elif self.is_locked:
            return "Untitled Locked Note.locked"
        elif hasattr(self, "default_title") and self.default_title:
            return self.default_title
        else:
            return "Untitled Document.txt"

    def update_theme_scheme(self, mode: str = None):
        if mode is None:
            mode = get_setting("theme_mode", "system")

        style_mgr = Adw.StyleManager.get_default()
        if mode == "oled":
            scheme = self.sm.get_scheme("oled-purple") or self.sm.get_scheme("Adwaita-dark")
        elif mode == "dark":
            scheme = self.sm.get_scheme("Adwaita-dark") or self.sm.get_scheme("classic-dark")
        elif mode == "light":
            scheme = self.sm.get_scheme("Adwaita") or self.sm.get_scheme("classic")
        else:  # "system"
            if style_mgr.get_dark():
                scheme = self.sm.get_scheme("Adwaita-dark") or self.sm.get_scheme("classic-dark")
            else:
                scheme = self.sm.get_scheme("Adwaita") or self.sm.get_scheme("classic")

        if scheme:
            self.buffer.set_style_scheme(scheme)

    def set_language_by_id(self, lang_id: str):
        if not lang_id or lang_id in ("none", "text", "plain"):
            self.buffer.set_language(None)
            self.selected_lang_id = None
        else:
            lang = self.lm.get_language(lang_id)
            if lang:
                self.buffer.set_language(lang)
                self.selected_lang_id = lang_id
            else:
                self.buffer.set_language(None)
                self.selected_lang_id = None

        if not self.filepath:
            if self.is_locked:
                self.default_title = "Untitled Locked Note.locked"
            elif not lang_id or lang_id in ("none", "text", "plain"):
                self.default_title = "Untitled Document.txt"
            elif lang_id == "markdown":
                self.default_title = "Untitled Note.md"
            elif lang_id == "python3":
                self.default_title = "Untitled.py"
            elif lang_id == "sh":
                self.default_title = "Untitled.sh"
            elif lang_id == "c":
                self.default_title = "Untitled.c"
            elif lang_id == "cpp":
                self.default_title = "Untitled.cpp"
            elif lang_id == "rust":
                self.default_title = "Untitled.rs"
            elif lang_id == "go":
                self.default_title = "Untitled.go"
            elif lang_id == "javascript":
                self.default_title = "Untitled.js"
            elif lang_id == "typescript":
                self.default_title = "Untitled.ts"
            elif lang_id == "html":
                self.default_title = "Untitled.html"
            elif lang_id == "css":
                self.default_title = "Untitled.css"
            elif lang_id == "json":
                self.default_title = "Untitled.json"
            elif lang_id == "yaml":
                self.default_title = "Untitled.yaml"
            elif lang_id == "toml":
                self.default_title = "Untitled.toml"
            elif lang_id == "sql":
                self.default_title = "Untitled.sql"
            else:
                self.default_title = f"Untitled.{lang_id}"

    def set_font_size(self, size_pt: int):
        self.font_size_pt = max(8, min(48, size_pt))
        css = f"textview.notes-editor {{ font-size: {self.font_size_pt}pt; }}"
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        self.editor.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # -------------------------------------------------------------------------
    # Real-Time Voice Streaming Buffer Integration
    # -------------------------------------------------------------------------
    def start_voice_stream(self):
        self._suppress_autocomplete = True
        self.is_voice_dictating = True
        self.clear_ghost_text()
        it = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        if self.voice_start_mark:
            self.buffer.delete_mark(self.voice_start_mark)
        if self.voice_end_mark:
            self.buffer.delete_mark(self.voice_end_mark)
        self.voice_start_mark = self.buffer.create_mark("voice_start", it, True)
        self.voice_end_mark = self.buffer.create_mark("voice_end", it, False)

    def append_voice_text(self, text: str, is_final: bool):
        if not text or not self.voice_start_mark or not self.voice_end_mark:
            return

        self.clear_ghost_text()
        self.buffer.begin_user_action()
        try:
            # 1. Delete previous partial text between start and end marks
            start_it = self.buffer.get_iter_at_mark(self.voice_start_mark)
            end_it = self.buffer.get_iter_at_mark(self.voice_end_mark)
            if start_it.compare(end_it) != 0:
                self.buffer.delete(start_it, end_it)

            # 2. Re-query start iterator after deletion
            start_it = self.buffer.get_iter_at_mark(self.voice_start_mark)

            prefix = ""
            if not start_it.is_start() and not start_it.starts_line():
                prev_it = start_it.copy()
                prev_it.backward_char()
                if prev_it.get_char() not in (" ", "\n", "\t"):
                    prefix = " "

            insert_str = prefix + text
            # Insert at start_mark. Since start_mark is left_gravity=True and end_mark is left_gravity=False,
            # start_mark remains at the beginning and end_mark moves to the end of the insertion.
            self.buffer.insert(start_it, insert_str)

            if is_final:
                # Commit sentence with a trailing space and advance start_mark
                end_it = self.buffer.get_iter_at_mark(self.voice_end_mark)
                self.buffer.insert(end_it, " ")
                new_start_it = self.buffer.get_iter_at_mark(self.voice_end_mark)
                self.buffer.move_mark(self.voice_start_mark, new_start_it)
        finally:
            self.buffer.end_user_action()

        # Scroll so user sees streaming words live
        self.editor.scroll_to_mark(self.voice_end_mark, 0.05, False, 0.0, 0.0)

    def finalize_voice_stream(self):
        self.buffer.begin_user_action()
        try:
            if self.voice_end_mark:
                end_it = self.buffer.get_iter_at_mark(self.voice_end_mark)
                if not end_it.is_start():
                    prev_it = end_it.copy()
                    prev_it.backward_char()
                    if prev_it.get_char() not in (" ", "\n", "\t"):
                        self.buffer.insert(end_it, " ")
            if self.voice_start_mark:
                self.buffer.delete_mark(self.voice_start_mark)
                self.voice_start_mark = None
            if self.voice_end_mark:
                self.buffer.delete_mark(self.voice_end_mark)
                self.voice_end_mark = None
        finally:
            self.buffer.end_user_action()
        self.is_voice_dictating = False
        self._suppress_autocomplete = False

    def cancel_voice_stream(self):
        self.buffer.begin_user_action()
        try:
            if self.voice_start_mark and self.voice_end_mark:
                start_it = self.buffer.get_iter_at_mark(self.voice_start_mark)
                end_it = self.buffer.get_iter_at_mark(self.voice_end_mark)
                if start_it.compare(end_it) != 0:
                    self.buffer.delete(start_it, end_it)
            if self.voice_start_mark:
                self.buffer.delete_mark(self.voice_start_mark)
                self.voice_start_mark = None
            if self.voice_end_mark:
                self.buffer.delete_mark(self.voice_end_mark)
                self.voice_end_mark = None
        finally:
            self.buffer.end_user_action()
        self.is_voice_dictating = False
        self._suppress_autocomplete = False


class LanguageSelectorPopover(Gtk.Popover):
    """
    Interactive popup allowing the user to select syntax highlighting & editor mode
    across 176+ languages (Markdown, Plain Text, Python, C, Rust, etc.).
    """
    POPULAR_LANGUAGES = [
        ("none", "Plain Text", "Raw unformatted text file (no markdown styling)"),
        ("markdown", "Markdown", "Markdown documentation & notes"),
        ("python3", "Python", "Python 3 source code"),
        ("sh", "Shell Script", "Bash / POSIX shell scripts"),
        ("c", "C", "C source code"),
        ("cpp", "C++", "C++ source code"),
        ("rust", "Rust", "Rust source code"),
        ("go", "Go", "Go source code"),
        ("javascript", "JavaScript", "JavaScript web scripts"),
        ("typescript", "TypeScript", "TypeScript typed code"),
        ("html", "HTML", "HyperText Markup Language"),
        ("css", "CSS", "Cascading Style Sheets"),
        ("json", "JSON", "JavaScript Object Notation"),
        ("yaml", "YAML", "YAML data & config"),
        ("toml", "TOML", "TOML configuration"),
        ("sql", "SQL", "Database query script"),
        ("xml", "XML", "Extensible Markup Language"),
        ("dockerfile", "Dockerfile", "Container build definitions"),
        ("ini", "INI / Config", "Desktop & system config files"),
    ]

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.lm = GtkSource.LanguageManager.get_default()
        self.set_size_request(300, 380)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        main_box.set_margin_top(8)
        main_box.set_margin_bottom(8)
        main_box.set_margin_start(8)
        main_box.set_margin_end(8)
        self.set_child(main_box)

        # Search Bar
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Filter languages...")
        self.search_entry.connect("search-changed", self._on_search_changed)
        main_box.append(self.search_entry)

        # Scrolled List
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        scrolled.set_min_content_height(300)
        main_box.append(scrolled)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class("boxed-list")
        self.list_box.connect("row-activated", self._on_row_activated)
        self.list_box.set_filter_func(self._filter_func)
        scrolled.set_child(self.list_box)

        self._populate()

    def _populate(self):
        seen_ids = set()
        for lang_id, name, desc in self.POPULAR_LANGUAGES:
            row = Gtk.ListBoxRow()
            row._lang_id = lang_id
            row._lang_name = name
            row._search_key = f"{name.lower()} {desc.lower()} {lang_id.lower()}"

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_margin_top(6)
            box.set_margin_bottom(6)
            box.set_margin_start(10)
            box.set_margin_end(10)

            lbl_name = Gtk.Label(label=name, xalign=0)
            lbl_name.add_css_class("heading")
            box.append(lbl_name)

            lbl_desc = Gtk.Label(label=desc, xalign=0)
            lbl_desc.add_css_class("dim-label")
            box.append(lbl_desc)

            row.set_child(box)
            self.list_box.append(row)
            seen_ids.add(lang_id)

        for lang_id in sorted(self.lm.get_language_ids()):
            if lang_id in seen_ids:
                continue
            lang = self.lm.get_language(lang_id)
            if not lang:
                continue
            name = lang.get_name()
            section = lang.get_section() or "Source Code"

            row = Gtk.ListBoxRow()
            row._lang_id = lang_id
            row._lang_name = name
            row._search_key = f"{name.lower()} {section.lower()} {lang_id.lower()}"

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_margin_top(6)
            box.set_margin_bottom(6)
            box.set_margin_start(10)
            box.set_margin_end(10)

            lbl_name = Gtk.Label(label=name, xalign=0)
            box.append(lbl_name)

            lbl_desc = Gtk.Label(label=section, xalign=0)
            lbl_desc.add_css_class("dim-label")
            box.append(lbl_desc)

            row.set_child(box)
            self.list_box.append(row)

    def _filter_func(self, row):
        query = self.search_entry.get_text().strip().lower()
        if not query:
            return True
        return query in getattr(row, "_search_key", "")

    def _on_search_changed(self, entry):
        self.list_box.invalidate_filter()

    def _on_row_activated(self, list_box, row):
        lang_id = getattr(row, "_lang_id", None)
        lang_name = getattr(row, "_lang_name", "Plain Text")
        self.window.set_current_page_language(lang_id, lang_name)
        self.popdown()


class NotesWindow(Adw.ApplicationWindow):
    def __init__(self, app, open_files=None, create_locked=False):
        super().__init__(application=app, title="Notes & Text Editor")
        self.set_default_size(1080, 750)
        self.add_css_class("notes-window")

        self.engine = AutocompleteEngine()
        self.voice_mgr = VoiceDictationManager()
        self.plugin_manager = PluginManager(self)

        self._build_ui()
        self._connect_signals()

        # Apply saved theme mode
        saved_theme = get_setting("theme_mode", "system")
        self.apply_theme_mode(saved_theme)

        style_mgr = Adw.StyleManager.get_default()
        style_mgr.connect("notify::dark", self._on_system_dark_changed)

        ensure_locked_files_in_locked_dir()

        if open_files:
            for f in open_files:
                self.open_tab_with_file(f)
        elif create_locked:
            self.open_new_tab(create_locked=True)
        else:
            self.open_new_tab()

    def _build_ui(self):
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root_box)

        # 1. HeaderBar
        self.header = Adw.HeaderBar()
        self.header.add_css_class("notes-header")
        root_box.append(self.header)

        # Left Header Actions: New Tab, Open, Save
        left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        self.btn_new = Gtk.Button.new_from_icon_name("tab-new-symbolic")
        self.btn_new.set_tooltip_text("New Tab (Ctrl+T / Ctrl+N)")
        self.btn_new.add_css_class("header-action-btn")
        self.btn_new.connect("clicked", lambda _: self.open_new_tab())
        left_box.append(self.btn_new)

        self.btn_open = Gtk.Button.new_from_icon_name("document-open-symbolic")
        self.btn_open.set_tooltip_text("Open File (Ctrl+O)")
        self.btn_open.add_css_class("header-action-btn")
        self.btn_open.connect("clicked", lambda _: self.on_action_open())
        left_box.append(self.btn_open)

        self.btn_save = Gtk.Button.new_from_icon_name("document-save-symbolic")
        self.btn_save.set_tooltip_text("Save File (Ctrl+S)")
        self.btn_save.add_css_class("header-action-btn")
        self.btn_save.connect("clicked", lambda _: self.on_action_save())
        left_box.append(self.btn_save)

        self.header.pack_start(left_box)

        # Right Header Actions: Find, Voice, AI, Obsidian, Lock, Menu
        right_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        self.btn_find = Gtk.Button.new_from_icon_name("system-search-symbolic")
        self.btn_find.set_tooltip_text("Find & Replace (Ctrl+F / Ctrl+H)")
        self.btn_find.add_css_class("header-action-btn")
        self.btn_find.connect("clicked", lambda _: self.toggle_search_bar())
        right_box.append(self.btn_find)

        self.btn_voice = Gtk.Button.new_from_icon_name("audio-input-microphone-symbolic")
        self.btn_voice.set_tooltip_text("Local Whisper Dictation (Ctrl+Alt+V)")
        self.btn_voice.add_css_class("header-action-btn")
        self.btn_voice.set_focusable(False)
        self.btn_voice.connect("clicked", lambda _: self.toggle_voice_dictation())
        right_box.append(self.btn_voice)

        self.btn_ai = Gtk.Button.new_from_icon_name("system-run-symbolic")
        self.btn_ai.set_tooltip_text("AI Assistant Prompt (Ctrl+Alt+A)")
        self.btn_ai.add_css_class("header-action-btn")
        self.btn_ai.connect("clicked", lambda _: self.trigger_ai_prompt())
        right_box.append(self.btn_ai)

        self.btn_ascii = Gtk.Button.new_from_icon_name("applications-graphics-symbolic")
        self.btn_ascii.set_tooltip_text("ASCII Art Archives & AI Synthesis (Ctrl+Shift+I / Ctrl+Alt+I)")
        self.btn_ascii.add_css_class("header-action-btn")
        self.btn_ascii.connect("clicked", lambda _: self.trigger_ascii_art())
        right_box.append(self.btn_ascii)

        self.btn_obsidian = Gtk.Button.new_from_icon_name("document-send-symbolic")
        self.btn_obsidian.set_tooltip_text("Push Note to Obsidian Vault (Ctrl+Alt+O)")
        self.btn_obsidian.add_css_class("header-action-btn")
        self.btn_obsidian.connect("clicked", lambda _: self.push_current_note_to_obsidian())
        right_box.append(self.btn_obsidian)

        self.btn_lock = Gtk.Button.new_from_icon_name("changes-prevent-symbolic")
        self.btn_lock.set_tooltip_text("Lock & Encrypt Note (AES-256-GCM)")
        self.btn_lock.add_css_class("header-action-btn")
        self.btn_lock.connect("clicked", lambda _: self.toggle_lock_state())
        right_box.append(self.btn_lock)

        # Main Hamburger Menu (≡)
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.add_css_class("header-action-btn")
        menu_button.set_tooltip_text("Main Menu")

        menu = Gio.Menu()
        menu.append("New Window", "win.new_window")
        menu.append("Save As...", "win.save_as")
        menu.append("Find and Replace...", "win.find_replace")

        # ASCII Art Integration
        ascii_section = Gio.Menu()
        ascii_section.append("Search Online ASCII Archives... (Ctrl+Shift+I)", "win.ascii_art_search")
        ascii_section.append("Generate AI ASCII Art... (Ctrl+Alt+I)", "win.ascii_art_generate")
        menu.append_section("ASCII Art", ascii_section)

        # Obsidian Vault Integration
        obsidian_section = Gio.Menu()
        obsidian_section.append("Push to Obsidian Vault (Ctrl+Alt+O)", "win.obsidian_push")
        obsidian_section.append("New Obsidian Note (Ctrl+Shift+O)", "win.obsidian_new")
        obsidian_section.append("Manage / Switch Vaults...", "win.obsidian_manage_vaults")
        obsidian_section.append("Choose Vault in File Manager...", "win.obsidian_choose_folder")
        menu.append_section("Obsidian", obsidian_section)

        # Plugins Submenu
        plugins_submenu = self.plugin_manager.build_plugins_menu()
        menu.append_submenu("Plugins", plugins_submenu)

        view_section = Gio.Menu()
        view_section.append("Zoom In", "win.zoom_in")
        view_section.append("Zoom Out", "win.zoom_out")
        view_section.append("Reset Zoom", "win.zoom_reset")
        view_section.append("Toggle Line Numbers", "win.toggle_line_numbers")
        view_section.append("Toggle Word Wrap", "win.toggle_word_wrap")
        view_section.append("Toggle Margin Guide (80)", "win.toggle_right_margin")
        menu.append_section("View Options", view_section)

        theme_section = Gio.Menu()
        theme_section.append("System Default", "win.theme_system")
        theme_section.append("Pure OLED Pitch Black (Reaper)", "win.theme_oled")
        theme_section.append("Dark Mode", "win.theme_dark")
        theme_section.append("Light Mode", "win.theme_light")
        menu.append_submenu("Appearance", theme_section)

        help_section = Gio.Menu()
        help_section.append("Keyboard Shortcuts", "win.shortcuts")
        menu.append_section(None, help_section)

        menu_button.set_menu_model(menu)
        right_box.append(menu_button)

        self.header.pack_end(right_box)

        # Action Progress Bar (thin purple line across top of window during save/push)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.add_css_class("action-progress-bar")
        self.progress_bar.set_visible(False)
        root_box.append(self.progress_bar)

        # 2. Tab Bar & Tab View
        self.tab_view = Adw.TabView()
        self.tab_view.connect("notify::selected-page", self._on_selected_tab_changed)
        self.tab_view.connect("close-page", self._on_close_page_requested)

        self.tab_bar = Adw.TabBar()
        self.tab_bar.set_view(self.tab_view)
        self.tab_bar.set_autohide(False)
        root_box.append(self.tab_bar)

        root_box.append(self.tab_view)

        # 3. Bottom Status Bar
        self.statusbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        self.statusbar.add_css_class("notes-statusbar")

        self.lbl_status = Gtk.Label(label="Ready")
        self.lbl_status.set_halign(Gtk.Align.START)
        self.lbl_status.set_hexpand(True)
        self.statusbar.append(self.lbl_status)

        self.lbl_suggestion = Gtk.Label(label="")
        self.lbl_suggestion.add_css_class("status-tag")
        self.statusbar.append(self.lbl_suggestion)

        self.lbl_cursor_pos = Gtk.Label(label="Ln 1, Col 1")
        self.statusbar.append(self.lbl_cursor_pos)

        self.lbl_stats = Gtk.Label(label="0 words | 0 chars")
        self.statusbar.append(self.lbl_stats)

        # Interactive Language / File Type Selector Popover
        self.pop_language = LanguageSelectorPopover(self)
        self.btn_language = Gtk.MenuButton()
        self.btn_language.set_popover(self.pop_language)
        self.btn_language.add_css_class("language-selector-btn")
        self.btn_language.set_tooltip_text("Change syntax highlighting & file type")
        self.btn_language.set_label("Markdown ▾")
        self.statusbar.append(self.btn_language)

        root_box.append(self.statusbar)

        self._setup_actions()

    def _setup_actions(self):
        actions = [
            ("new_window", lambda *_: self.get_application().activate()),
            ("save_as", lambda *_: self.on_action_save_as()),
            ("find_replace", lambda *_: self.toggle_search_bar(show_replace=True)),
            ("zoom_in", lambda *_: self.zoom(1)),
            ("zoom_out", lambda *_: self.zoom(-1)),
            ("zoom_reset", lambda *_: self.zoom(0)),
            ("toggle_line_numbers", lambda *_: self.toggle_line_numbers()),
            ("toggle_word_wrap", lambda *_: self.toggle_word_wrap()),
            ("toggle_right_margin", lambda *_: self.toggle_right_margin()),
            ("shortcuts", lambda *_: self.show_shortcuts_dialog()),
            ("theme_system", lambda *_: self.apply_theme_mode("system")),
            ("theme_oled", lambda *_: self.apply_theme_mode("oled")),
            ("theme_dark", lambda *_: self.apply_theme_mode("dark")),
            ("theme_light", lambda *_: self.apply_theme_mode("light")),
            ("obsidian_push", lambda *_: self.push_current_note_to_obsidian()),
            ("obsidian_new", lambda *_: self.create_new_obsidian_note()),
            ("obsidian_manage_vaults", lambda *_: self.show_obsidian_vaults()),
            ("obsidian_choose_folder", lambda *_: self.choose_obsidian_folder()),
            ("ascii_art_generate", lambda *_: self.trigger_ascii_art()),
            ("ascii_art_search", lambda *_: self.trigger_ascii_art_search()),
            ("show_plugins_manager", lambda *_: self.plugin_manager.show_manager_dialog()),
            ("open_plugins_folder", lambda *_: self.open_plugins_folder()),
        ]
        for name, callback in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def _connect_signals(self):
        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_ctrl)
        self.connect("close-request", self._on_window_close_requested)

    def trigger_action_progress(self, duration_ms: int = 500):
        """Animates a subtle purple progress line across the window like GNOME Text Editor."""
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        steps = 15
        interval = max(15, duration_ms // steps)
        current_step = 0

        def on_step():
            nonlocal current_step
            current_step += 1
            self.progress_bar.set_fraction(current_step / steps)
            if current_step >= steps:
                GLib.timeout_add(150, lambda: self.progress_bar.set_visible(False))
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        GLib.timeout_add(interval, on_step)

    def _save_page_immediately(self, page: EditorPage) -> bool:
        """Saves a modified page immediately without blocking async modal stalls."""
        clean_text = page.get_clean_text()
        if not clean_text.strip():
            page.is_modified = False
            return True

        if not page.filepath:
            first_line = ""
            for line in clean_text.splitlines():
                s = line.strip().lstrip("#").strip()
                if s:
                    first_line = s
                    break
            safe_name = "".join(c for c in (first_line or "Note") if c.isalnum() or c in (" ", "-", "_")).strip()
            if not safe_name:
                safe_name = f"Note_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            ext = ".locked" if page.is_locked else ".txt"
            target_dir = LOCKED_NOTES_DIR if page.is_locked else DEFAULT_NOTES_DIR
            target_dir.mkdir(parents=True, exist_ok=True)

            candidate = target_dir / f"{safe_name}{ext}"
            counter = 1
            while candidate.exists():
                candidate = target_dir / f"{safe_name}_{counter}{ext}"
                counter += 1
            page.filepath = str(candidate)
        else:
            if page.is_locked:
                ensure_page_locked_storage(page)
            elif Path(page.filepath).parent.resolve() == LOCKED_NOTES_DIR.resolve():
                ensure_page_unlocked_storage(page)

        path = Path(page.filepath)
        try:
            if page.is_locked:
                payload = encrypt_note(clean_text)
                with open(path, "wb") as f:
                    f.write(payload)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(clean_text)
            page.is_modified = False
            self.update_tab_title(page)
            return True
        except Exception as e:
            print(f"Error auto-saving note {path}: {e}", file=sys.stderr)
            return False

    def _on_window_close_requested(self, window):
        """Checks for modified/unsaved tabs before allowing the window to close."""
        modified_pages = []
        for i in range(self.tab_view.get_n_pages()):
            adw_page = self.tab_view.get_nth_page(i)
            child = adw_page.get_child()
            if child and child.is_modified and len(child.get_clean_text().strip()) > 0:
                modified_pages.append((adw_page, child))

        if not modified_pages:
            return False

        # If auto-save is enabled, automatically save all modified notes immediately and exit cleanly
        if get_setting("auto_save", True):
            for _, page in modified_pages:
                self._save_page_immediately(page)
            return False

        if len(modified_pages) == 1:
            title = modified_pages[0][1].get_title()
            heading = f'Save changes to "{title}" before closing?'
            body = "If you close without saving, your changes will be discarded."
        else:
            heading = f"Save changes to {len(modified_pages)} open notes before closing?"
            body = "There are unsaved changes. Discarding will permanently lose them."

        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=heading,
            body=body,
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("discard", "Discard All")
        dialog.add_response("save", "Save All" if len(modified_pages) > 1 else "Save")
        dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def on_response(d, response):
            if response == "save":
                for _, page in modified_pages:
                    self._save_page_immediately(page)
                self.destroy()
            elif response == "discard":
                for _, page in modified_pages:
                    page.is_modified = False
                self.destroy()

        dialog.connect("response", on_response)
        dialog.present()
        return True

    def rename_active_document(self, new_name: str, move_file: bool = True):
        """Renames the current document tab and underlying file on disk (if saved)."""
        page = self.get_current_page()
        if not page:
            return

        safe_name = "".join(c for c in new_name if c.isalnum() or c in (" ", "-", "_", ".")).strip()
        if not safe_name:
            safe_name = "Untitled Note"

        ext = Path(safe_name).suffix
        if not ext:
            ext = ".locked" if page.is_locked else ".txt"
            safe_name += ext
        elif page.is_locked and ext != ".locked":
            safe_name = f"{Path(safe_name).stem}.locked"

        if page.filepath:
            old_path = Path(page.filepath)
            parent_dir = LOCKED_NOTES_DIR if page.is_locked else (DEFAULT_NOTES_DIR if old_path.parent.resolve() == LOCKED_NOTES_DIR.resolve() and not page.is_locked else old_path.parent)
            parent_dir.mkdir(parents=True, exist_ok=True)
            new_path = parent_dir / safe_name
            if move_file and old_path.exists() and old_path != new_path:
                try:
                    old_path.rename(new_path)
                except Exception as e:
                    print(f"Failed to rename file on disk: {e}", file=sys.stderr)
            page.filepath = str(new_path)
            page._detect_and_set_language(page.filepath)
        else:
            page.default_title = safe_name

        self.update_tab_title(page)
        self.update_status_bar()
        self.set_status_message(f"Renamed note to: {safe_name}")

    def get_current_page(self) -> EditorPage:
        adw_page = self.tab_view.get_selected_page()
        if adw_page:
            return adw_page.get_child()
        return None

    def open_new_tab(self, create_locked=False) -> EditorPage:
        page = EditorPage(self, create_locked=create_locked)
        adw_page = self.tab_view.append(page)
        adw_page.set_title(page.get_title())
        adw_page.set_icon(Gio.ThemedIcon.new("channel-secure-symbolic" if create_locked else "text-x-generic-symbolic"))
        self.tab_view.set_selected_page(adw_page)
        self.update_lock_button_state()
        page.editor.grab_focus()
        return page

    def open_tab_with_file(self, filepath: str) -> EditorPage:
        # If active page is empty and untitled, reuse it
        curr = self.get_current_page()
        if curr and not curr.filepath and not curr.is_modified and len(curr.get_clean_text().strip()) == 0:
            curr.load_file(filepath)
            self.update_lock_button_state()
            return curr

        page = EditorPage(self, filepath=filepath)
        adw_page = self.tab_view.append(page)
        adw_page.set_title(page.get_title())
        adw_page.set_icon(Gio.ThemedIcon.new("channel-secure-symbolic" if page.is_locked else "text-x-generic-symbolic"))
        self.tab_view.set_selected_page(adw_page)
        self.update_lock_button_state()
        page.editor.grab_focus()
        return page

    def update_tab_title(self, editor_page: EditorPage):
        for i in range(self.tab_view.get_n_pages()):
            adw_page = self.tab_view.get_nth_page(i)
            if adw_page.get_child() == editor_page:
                title = editor_page.get_title()
                if editor_page.is_modified:
                    title = "• " + title
                adw_page.set_title(title)
                adw_page.set_icon(Gio.ThemedIcon.new("channel-secure-symbolic" if editor_page.is_locked else "text-x-generic-symbolic"))
                break

    def _on_selected_tab_changed(self, tab_view, param):
        self.update_status_bar()
        self.update_lock_button_state()

    def _on_close_page_requested(self, tab_view, adw_page):
        page = adw_page.get_child()
        if page and page.is_modified and len(page.get_clean_text().strip()) > 0:
            if get_setting("auto_save", True):
                self._save_page_immediately(page)
                tab_view.close_page_finish(adw_page, True)
                if tab_view.get_n_pages() == 0:
                    self.open_new_tab()
                return True

            dialog = Adw.MessageDialog(
                transient_for=self,
                heading=f'Save changes to "{page.get_title()}"?',
                body="If you close without saving, your changes will be discarded."
            )
            dialog.add_response("cancel", "Cancel")
            dialog.add_response("discard", "Discard")
            dialog.add_response("save", "Save")
            dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

            def on_response(d, response):
                if response == "save":
                    self._save_page_immediately(page)
                    tab_view.close_page_finish(adw_page, True)
                elif response == "discard":
                    page.is_modified = False
                    tab_view.close_page_finish(adw_page, True)
                else:
                    tab_view.close_page_finish(adw_page, False)

            dialog.connect("response", on_response)
            dialog.present()
            return True

        tab_view.close_page_finish(adw_page, True)
        if tab_view.get_n_pages() == 0:
            self.open_new_tab()
        return True

    def update_status_bar(self):
        page = self.get_current_page()
        if not page:
            return

        # Cursor Position
        insert_mark = page.buffer.get_insert()
        cursor_iter = page.buffer.get_iter_at_mark(insert_mark)
        line = cursor_iter.get_line() + 1
        col = cursor_iter.get_line_offset() + 1
        self.lbl_cursor_pos.set_text(f"Ln {line}, Col {col}")

        # Stats
        text = page.get_clean_text()
        words = len(text.split())
        chars = len(text)
        self.lbl_stats.set_text(f"{words} words | {chars} chars")

        # Language
        lang = page.buffer.get_language()
        lang_name = lang.get_name() if lang else "Plain Text"
        self.btn_language.set_label(f"{lang_name} ▾")

        # Status text
        if page.filepath:
            lock_prefix = "🔒 " if page.is_locked else ""
            self.lbl_status.set_text(f"{lock_prefix}{page.filepath}")
        elif page.is_locked:
            self.lbl_status.set_text("🔒 Biometric encryption active (AES-256-GCM)")
        else:
            self.lbl_status.set_text("Ready")

    def set_status_message(self, msg: str):
        self.lbl_status.set_text(msg)

    def update_lock_button_state(self):
        page = self.get_current_page()
        if not page:
            return
        if page.is_locked:
            self.btn_lock.set_icon_name("changes-allow-symbolic")
            self.btn_lock.set_tooltip_text("Unlock Note (Biometric authorization required)")
            self.btn_lock.add_css_class("locked-btn-active")
        else:
            self.btn_lock.set_icon_name("changes-prevent-symbolic")
            self.btn_lock.set_tooltip_text("Lock & Encrypt Note (AES-256-GCM)")
            self.btn_lock.remove_css_class("locked-btn-active")

    def set_current_page_language(self, lang_id: str, lang_name: str):
        page = self.get_current_page()
        if not page:
            return
        page.set_language_by_id(lang_id)
        set_setting("default_language", lang_id)
        self.update_tab_title(page)
        self.update_status_bar()
        self.set_status_message(f"Language set to: {lang_name}")

    def apply_theme_mode(self, mode: str):
        set_setting("theme_mode", mode)
        style_mgr = Adw.StyleManager.get_default()

        if mode == "oled":
            style_mgr.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            self.add_css_class("oled-mode")
        elif mode == "dark":
            style_mgr.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            self.remove_css_class("oled-mode")
        elif mode == "light":
            style_mgr.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
            self.remove_css_class("oled-mode")
        else:  # "system"
            style_mgr.set_color_scheme(Adw.ColorScheme.DEFAULT)
            self.remove_css_class("oled-mode")

        for i in range(self.tab_view.get_n_pages()):
            page = self.tab_view.get_nth_page(i).get_child()
            page.update_theme_scheme(mode)

        self.set_status_message(f"Theme updated: {mode.title()}")

    def _on_system_dark_changed(self, style_mgr, param):
        saved_theme = get_setting("theme_mode", "system")
        if saved_theme == "system":
            self.apply_theme_mode("system")

    # -------------------------------------------------------------------------
    # Hotkeys & Keyboard Navigation
    # -------------------------------------------------------------------------
    def on_key_pressed(self, controller, keyval, keycode, state):
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        alt = bool(state & Gdk.ModifierType.ALT_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)

        page = self.get_current_page()

        # Escape -> Cancel Voice Dictation or Close Search Bar
        if keyval == Gdk.KEY_Escape:
            if self.voice_mgr.is_active():
                self.cancel_voice_dictation()
                return True
            if page and page.search_box.get_visible():
                page.hide_search()
                return True

        # Hotkey: Ctrl+Alt+V or F9 -> Voice Dictation
        if (ctrl and alt and keyval in (Gdk.KEY_v, Gdk.KEY_V)) or keyval == Gdk.KEY_F9:
            self.toggle_voice_dictation()
            return True

        # Hotkey: Ctrl+Alt+A -> AI Assistant Prompt
        if ctrl and alt and keyval in (Gdk.KEY_a, Gdk.KEY_A):
            self.trigger_ai_prompt()
            return True

        # Hotkey: Ctrl+Alt+I -> Generate ASCII Art
        if ctrl and alt and keyval in (Gdk.KEY_i, Gdk.KEY_I):
            self.trigger_ascii_art()
            return True

        # Hotkey: Ctrl+Shift+I -> Search Online ASCII Art Archives
        if ctrl and shift and keyval in (Gdk.KEY_i, Gdk.KEY_I):
            self.trigger_ascii_art_search()
            return True

        # Hotkey: Ctrl+Alt+O -> Push Note to Obsidian Vault
        if ctrl and alt and keyval in (Gdk.KEY_o, Gdk.KEY_O):
            self.push_current_note_to_obsidian()
            return True

        # Hotkey: Ctrl+Shift+O -> New Obsidian Note
        if ctrl and shift and keyval in (Gdk.KEY_o, Gdk.KEY_O):
            self.create_new_obsidian_note()
            return True

        # Hotkey: Ctrl+Shift+S -> Save As
        if ctrl and shift and keyval in (Gdk.KEY_s, Gdk.KEY_S):
            self.on_action_save_as()
            return True

        # Hotkey: Ctrl+S -> Save
        if ctrl and not alt and not shift and keyval in (Gdk.KEY_s, Gdk.KEY_S):
            self.on_action_save()
            return True

        # Hotkey: Ctrl+O -> Open
        if ctrl and not alt and not shift and keyval in (Gdk.KEY_o, Gdk.KEY_O):
            self.on_action_open()
            return True

        # Hotkey: Ctrl+T or Ctrl+N -> New Tab
        if ctrl and not alt and not shift and keyval in (Gdk.KEY_t, Gdk.KEY_T, Gdk.KEY_n, Gdk.KEY_N):
            self.open_new_tab()
            return True

        # Hotkey: Ctrl+Shift+N -> New Window
        if ctrl and shift and keyval in (Gdk.KEY_n, Gdk.KEY_N):
            self.get_application().activate()
            return True

        # Hotkey: Ctrl+W -> Close Tab
        if ctrl and not alt and not shift and keyval in (Gdk.KEY_w, Gdk.KEY_W):
            adw_page = self.tab_view.get_selected_page()
            if adw_page:
                self.tab_view.close_page(adw_page)
            return True

        # Hotkey: Ctrl+F -> Find
        if ctrl and not alt and not shift and keyval in (Gdk.KEY_f, Gdk.KEY_F):
            if page:
                page.show_search(show_replace=False)
            return True

        # Hotkey: Ctrl+H -> Find and Replace
        if ctrl and not alt and not shift and keyval in (Gdk.KEY_h, Gdk.KEY_H):
            if page:
                page.show_search(show_replace=True)
            return True

        # Zoom: Ctrl+= / Ctrl++ (Zoom In), Ctrl+- (Zoom Out), Ctrl+0 (Reset)
        if ctrl and keyval in (Gdk.KEY_equal, Gdk.KEY_plus, Gdk.KEY_KP_Add):
            self.zoom(1)
            return True
        if ctrl and keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self.zoom(-1)
            return True
        if ctrl and keyval in (Gdk.KEY_0, Gdk.KEY_KP_0):
            self.zoom(0)
            return True

        # Ghost Text Acceptance: Tab or Right Arrow
        if page and page.active_ghost_text:
            if keyval == Gdk.KEY_Tab:
                page.commit_ghost_text()
                return True
            elif keyval == Gdk.KEY_Right:
                page.commit_ghost_text()
                return True
            elif keyval in (Gdk.KEY_Escape, Gdk.KEY_Return, Gdk.KEY_BackSpace):
                page.clear_ghost_text()

        return False

    def toggle_search_bar(self, show_replace=False):
        page = self.get_current_page()
        if not page:
            return
        if page.search_box.get_visible() and not show_replace:
            page.hide_search()
        else:
            page.show_search(show_replace=show_replace)

    def zoom(self, delta: int):
        page = self.get_current_page()
        if not page:
            return
        if delta == 0:
            page.set_font_size(DEFAULT_FONT_SIZE)
        else:
            page.set_font_size(page.font_size_pt + (delta * 2))
        self.set_status_message(f"Zoom: {int(page.font_size_pt / DEFAULT_FONT_SIZE * 100)}%")

    def toggle_line_numbers(self):
        page = self.get_current_page()
        if page:
            curr = page.editor.get_show_line_numbers()
            new_val = not curr
            page.editor.set_show_line_numbers(new_val)
            set_setting("line_numbers", new_val)

    def toggle_word_wrap(self):
        page = self.get_current_page()
        if page:
            curr = page.editor.get_wrap_mode()
            new_mode = Gtk.WrapMode.NONE if curr != Gtk.WrapMode.NONE else Gtk.WrapMode.WORD_CHAR
            page.editor.set_wrap_mode(new_mode)
            set_setting("word_wrap", new_mode != Gtk.WrapMode.NONE)

    def toggle_right_margin(self):
        page = self.get_current_page()
        if page:
            curr = page.editor.get_show_right_margin()
            new_val = not curr
            page.editor.set_show_right_margin(new_val)
            set_setting("right_margin", new_val)

    # -------------------------------------------------------------------------
    # Actions: Open & Save
    # -------------------------------------------------------------------------
    def on_action_open(self):
        dialog = Gtk.FileDialog()
        dialog.set_title("Open Document / Note")
        page = self.get_current_page()
        initial_dir = LOCKED_NOTES_DIR if (page and page.is_locked) else DEFAULT_NOTES_DIR
        initial_dir.mkdir(parents=True, exist_ok=True)
        dialog.set_initial_folder(Gio.File.new_for_path(str(initial_dir)))

        dialog.open_multiple(self, None, self._on_open_multiple_response)

    def _on_open_multiple_response(self, dialog, result):
        try:
            glist = dialog.open_multiple_finish(result)
            if glist:
                for i in range(glist.get_n_items()):
                    gfile = glist.get_item(i)
                    if gfile:
                        self.open_tab_with_file(gfile.get_path())
        except Exception:
            pass

    def on_action_save(self):
        page = self.get_current_page()
        if not page:
            return

        if not page.filepath:
            self.on_action_save_as()
            return

        if page.is_locked:
            ensure_page_locked_storage(page)
            page._detect_and_set_language(page.filepath)
        elif Path(page.filepath).parent.resolve() == LOCKED_NOTES_DIR.resolve():
            ensure_page_unlocked_storage(page)
            page._detect_and_set_language(page.filepath)

        self.trigger_action_progress(400)
        clean_text = page.get_clean_text()
        path = Path(page.filepath)

        if page.is_locked:
            payload = encrypt_note(clean_text)
            with open(path, "wb") as f:
                f.write(payload)
            page.is_modified = False
            self.update_tab_title(page)
            self.set_status_message(f"🔒 Saved encrypted note: {path.name}")
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(clean_text)
            page.is_modified = False
            self.update_tab_title(page)
            self.set_status_message(f"✅ Saved: {path.name}")

    def on_action_save_as(self):
        page = self.get_current_page()
        if not page:
            return

        dialog = Gtk.FileDialog()
        dialog.set_title("Save Document As...")
        suggested_name = page.get_title().replace("• ", "")
        if page.is_locked and not suggested_name.endswith(".locked"):
            suggested_name = f"{Path(suggested_name).stem}.locked"
        dialog.set_initial_name(suggested_name)

        initial_dir = LOCKED_NOTES_DIR if page.is_locked else DEFAULT_NOTES_DIR
        initial_dir.mkdir(parents=True, exist_ok=True)
        dialog.set_initial_folder(Gio.File.new_for_path(str(initial_dir)))

        dialog.save(self, None, self._on_save_as_response)

    def _on_save_as_response(self, dialog, result):
        try:
            gfile = dialog.save_finish(result)
            if gfile:
                page = self.get_current_page()
                if page:
                    chosen_path = Path(gfile.get_path())
                    if page.is_locked:
                        LOCKED_NOTES_DIR.mkdir(parents=True, exist_ok=True)
                        stem = chosen_path.stem if not chosen_path.name.endswith(".locked") else chosen_path.stem
                        filename = f"{stem}.locked"
                        target_path = LOCKED_NOTES_DIR / filename
                        page.filepath = str(target_path)
                    else:
                        page.filepath = str(chosen_path)
                    page._detect_and_set_language(page.filepath)
                    self.on_action_save()
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Biometric Locking
    # -------------------------------------------------------------------------
    def toggle_lock_state(self):
        page = self.get_current_page()
        if not page:
            return

        if not page.is_locked:
            if authenticate_biometric("enable locked note protection"):
                page.is_locked = True
                page.is_modified = True
                if page.filepath:
                    ensure_page_locked_storage(page)
                    page._detect_and_set_language(page.filepath)
                    self.on_action_save()
                else:
                    page.default_title = "Untitled Locked Note.locked"
                self.update_tab_title(page)
                self.update_lock_button_state()
                self.update_status_bar()
                self.set_status_message("🔒 Biometric lock engaged. Saved to Locked folder (AES-256-GCM).")
            else:
                self.set_status_message("⚠️ Biometric authorization required to lock note.")
        else:
            if authenticate_biometric("unlock note to plaintext"):
                page.is_locked = False
                page.is_modified = True
                if page.filepath:
                    ensure_page_unlocked_storage(page)
                    page._detect_and_set_language(page.filepath)
                    self.on_action_save()
                else:
                    page.default_title = "Untitled Document.txt"
                self.update_tab_title(page)
                self.update_lock_button_state()
                self.update_status_bar()
                self.set_status_message("🔓 Document unlocked to standard unencrypted format in Notes.")
            else:
                self.set_status_message("⚠️ Biometric authorization required to unlock note.")

    # -------------------------------------------------------------------------
    # Local Whisper Voice Dictation
    # -------------------------------------------------------------------------
    # Local Whisper Real-Time Streaming Voice Dictation
    # -------------------------------------------------------------------------
    def toggle_voice_dictation(self):
        page = self.get_current_page()
        if not page:
            return

        if not self.voice_mgr.is_active():
            page.start_voice_stream()
            page.editor.grab_focus()
            success = self.voice_mgr.start_streaming(
                on_partial_cb=self._on_voice_partial,
                on_complete_cb=self._on_voice_complete,
                on_error_cb=self._on_voice_error
            )
            if success:
                self.btn_voice.add_css_class("voice-btn-recording")
                self.btn_voice.set_icon_name("media-record-symbolic")
                self.btn_voice.set_tooltip_text("Stop Dictation (Click or Ctrl+Alt+V / F9 | Esc to cancel)")
                self.set_status_message("🎙️ Listening... (Words stream live onto screen | Esc to cancel)")
            else:
                self.set_status_message("❌ Failed to initialize PipeWire microphone.")
        else:
            self.stop_voice_dictation()

    def stop_voice_dictation(self):
        self.btn_voice.remove_css_class("voice-btn-recording")
        self.btn_voice.set_icon_name("audio-input-microphone-symbolic")
        self.btn_voice.set_tooltip_text("Local Whisper Dictation (Ctrl+Alt+V / F9)")
        self.set_status_message("🎙️ Finalizing dictation...")
        self.voice_mgr.stop_streaming()

    def cancel_voice_dictation(self):
        self.btn_voice.remove_css_class("voice-btn-recording")
        self.btn_voice.set_icon_name("audio-input-microphone-symbolic")
        self.btn_voice.set_tooltip_text("Local Whisper Dictation (Ctrl+Alt+V / F9)")
        self.voice_mgr.cancel_streaming()
        page = self.get_current_page()
        if page:
            page.cancel_voice_stream()
        self.set_status_message("Dictation canceled.")

    def _on_voice_partial(self, text: str, is_final: bool):
        page = self.get_current_page()
        if page:
            page.append_voice_text(text, is_final)
        preview = text if len(text) < 40 else text[:37] + "..."
        state_label = "Finalized" if is_final else "Listening"
        self.set_status_message(f"🎙️ {state_label}: \"{preview}\" (Esc to cancel)")

    def _on_voice_complete(self):
        self.btn_voice.remove_css_class("voice-btn-recording")
        self.btn_voice.set_icon_name("audio-input-microphone-symbolic")
        self.btn_voice.set_tooltip_text("Local Whisper Dictation (Ctrl+Alt+V / F9)")
        page = self.get_current_page()
        if page:
            page.finalize_voice_stream()
            page.editor.grab_focus()
        self.set_status_message("✅ Voice dictation completed.")

    def _on_voice_error(self, err_msg: str):
        self.btn_voice.remove_css_class("voice-btn-recording")
        self.btn_voice.set_icon_name("audio-input-microphone-symbolic")
        self.btn_voice.set_tooltip_text("Local Whisper Dictation (Ctrl+Alt+V / F9)")
        page = self.get_current_page()
        if page:
            page.cancel_voice_stream()
        self.set_status_message(f"❌ Microphone Error: {err_msg}")

    # -------------------------------------------------------------------------
    # Antigravity AI Task Dispatch (Safe Interactive Dialog)
    # -------------------------------------------------------------------------
    def trigger_ai_prompt(self):
        ai_plug = self.plugin_manager.get_plugin("ai_assistant")
        if ai_plug and ai_plug.enabled:
            ai_plug.prompt_dialog(self)
        else:
            self._legacy_ai_prompt()

    def trigger_ascii_art(self):
        """Presents ASCII art generator dialog or converts subject/image to ASCII."""
        ascii_plug = self.plugin_manager.get_plugin("ascii_art")
        if ascii_plug and ascii_plug.enabled:
            ascii_plug.show_prompt_dialog(self)
        else:
            self.set_status_message("⚠️ ASCII Art plugin is not loaded.")

    def trigger_ascii_art_search(self):
        """Presents online ASCII art search dialog across archives."""
        ascii_plug = self.plugin_manager.get_plugin("ascii_art")
        if ascii_plug and ascii_plug.enabled:
            ascii_plug.show_online_search_dialog(self)
        else:
            self.set_status_message("⚠️ ASCII Art plugin is not loaded.")

    def _legacy_ai_prompt(self):
        page = self.get_current_page()
        if not page:
            return

        page.clear_ghost_text()
        default_prompt = ""
        bounds = page.buffer.get_selection_bounds()
        if bounds:
            default_prompt = page.buffer.get_text(bounds[0], bounds[1], True).strip()

        # Present an interactive modal dialog so AI is never triggered accidentally
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="🤖 AI Assistant Prompt",
            body="Enter your prompt or instruction for AI completion:"
        )

        entry = Gtk.Entry()
        entry.set_placeholder_text("e.g. Summarize these notes, fix formatting, or generate outline...")
        if default_prompt:
            entry.set_text(default_prompt)
        entry.set_margin_top(8)
        entry.set_margin_bottom(8)
        entry.set_margin_start(16)
        entry.set_margin_end(16)
        dialog.set_extra_child(entry)

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("generate", "Generate")
        dialog.set_response_appearance("generate", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("generate")
        dialog.set_close_response("cancel")

        def on_response(dlg, response):
            if response == "generate":
                prompt_text = entry.get_text().strip()
                if not prompt_text:
                    self.set_status_message("⚠️ Prompt cannot be empty.")
                    return
                self.btn_ai.add_css_class("ai-btn-thinking")
                self.set_status_message(f"🤖 AI thinking: \"{prompt_text[:35]}...\"")
                dispatch_antigravity_prompt(prompt_text, self._on_ai_completed)
            else:
                self.set_status_message("AI prompt canceled.")

        dialog.connect("response", on_response)
        entry.connect("activate", lambda _: dialog.response("generate"))
        dialog.present()

    def _on_ai_completed(self, response: str):
        self.btn_ai.remove_css_class("ai-btn-thinking")
        page = self.get_current_page()
        if not page:
            return

        if response:
            page.clear_ghost_text()
            it = page.buffer.get_iter_at_mark(page.buffer.get_insert())
            insert_text = f"\n\n{response}\n"
            page.buffer.insert(it, insert_text)
            self.set_status_message("✅ AI response inserted!")
        else:
            self.set_status_message("⚠️ AI returned empty response.")

    def push_current_note_to_obsidian(self):
        """Pushes active document to the default Obsidian vault."""
        self.trigger_action_progress(600)
        obsidian_plug = self.plugin_manager.get_plugin("obsidian_sync")
        if obsidian_plug and obsidian_plug.enabled:
            obsidian_plug.push_note(self)
        else:
            page = self.get_current_page()
            if not page:
                self.set_status_message("⚠️ No active note to push.")
                return
            content = page.get_clean_text()
            if not content.strip():
                self.set_status_message("⚠️ Note is empty.")
                return
            raw_title = page.get_title()
            title = "" if "Untitled" in raw_title else raw_title
            default_vault = get_default_vault()
            if default_vault:
                vault_name, vault_path = default_vault
                success, res = push_to_obsidian(content, title, vault_path)
                if success:
                    page.filepath = res
                    page.is_modified = False
                    self.update_tab_title(page)
                    self.set_status_message(f"🟣 Pushed to Obsidian vault '{vault_name}': {Path(res).name}")
                else:
                    self.set_status_message(f"❌ Failed to push note: {res}")
            else:
                self.set_status_message("⚠️ No Obsidian vault detected on system.")

    def create_new_obsidian_note(self):
        """Creates a new note tab pre-formatted for Obsidian."""
        obsidian_plug = self.plugin_manager.get_plugin("obsidian_sync")
        if obsidian_plug and obsidian_plug.enabled:
            obsidian_plug.new_obsidian_note(self)
        else:
            page = self.open_new_tab()
            template = create_obsidian_template("New Obsidian Note")
            page.buffer.set_text(template)
            page.set_language_by_id("markdown")
            page.default_title = "New Obsidian Note.md"
            self.update_tab_title(page)
            self.set_status_message("🟣 Created new Obsidian note.")

    def show_obsidian_vaults(self):
        """Displays the Obsidian Vault Manager dialog."""
        obsidian_plug = self.plugin_manager.get_plugin("obsidian_sync")
        if obsidian_plug:
            obsidian_plug.show_vault_manager_dialog(self)

    def choose_obsidian_folder(self):
        """Opens native file manager to pick an Obsidian vault folder."""
        obsidian_plug = self.plugin_manager.get_plugin("obsidian_sync")
        if obsidian_plug:
            obsidian_plug.select_vault_from_file_manager(self)

    def open_plugins_folder(self):
        """Opens user plugins folder in file manager."""
        USER_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            Gio.AppInfo.launch_default_for_uri(USER_PLUGINS_DIR.as_uri(), None)
        except Exception:
            import subprocess
            subprocess.Popen(["xdg-open", str(USER_PLUGINS_DIR)])

    def show_shortcuts_dialog(self):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Keyboard Shortcuts",
            body=(
                "• Ctrl+T / Ctrl+N : New Tab\n"
                "• Ctrl+Shift+N : New Window\n"
                "• Ctrl+W : Close Tab\n"
                "• Ctrl+O : Open Document\n"
                "• Ctrl+S : Save Document\n"
                "• Ctrl+Shift+S : Save As...\n"
                "• Ctrl+Alt+O : Push Note to Obsidian Vault\n"
                "• Ctrl+Shift+O : New Obsidian Note\n"
                "• Ctrl+F : Find in Document\n"
                "• Ctrl+H : Find and Replace\n"
                "• Tab / Right : Accept Ghost-Text Suggestion\n"
                "• Ctrl+Alt+V / F9 : Real-Time Voice Dictation (Esc to cancel)\n"
                "• Ctrl+Alt+A : AI Assistant Prompt\n"
                "• Ctrl+Alt+I : Generate AI ASCII Art\n"
                "• Ctrl+Shift+I : Search Online ASCII Art Archives\n"
                "• Ctrl++ / Ctrl+- : Zoom In / Out\n"
                "• Ctrl+0 : Reset Zoom"
            )
        )
        dialog.add_response("ok", "Close")
        dialog.present()


class NotesApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="com.reaper.Notes",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        )

    def do_startup(self):
        Adw.Application.do_startup(self)
        self._load_styles()

    def _load_styles(self):
        display = Gdk.Display.get_default()
        if not display:
            return
        provider = Gtk.CssProvider()
        if THEME_CSS_PATH.exists():
            provider.load_from_path(str(THEME_CSS_PATH))
            Gtk.StyleContext.add_provider_for_display(
                display,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        styles_dir = Path(__file__).resolve().parent / "styles"
        if styles_dir.exists():
            GtkSource.StyleSchemeManager.get_default().append_search_path(str(styles_dir))

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = NotesWindow(self)
        win.present()

    def do_command_line(self, command_line):
        args = command_line.get_arguments()
        open_files = []
        create_locked = False
        insert_text = None
        rename_title = None

        i = 1
        while i < len(args):
            arg = args[i]
            if arg in ("--locked", "-l", "--new-locked"):
                create_locked = True
            elif arg in ("--new", "-n"):
                pass
            elif arg == "--insert-text" and i + 1 < len(args):
                i += 1
                insert_text = args[i]
            elif arg == "--insert-file" and i + 1 < len(args):
                i += 1
                try:
                    insert_text = Path(args[i]).read_text(encoding="utf-8")
                except Exception:
                    pass
            elif arg == "--rename-active" and i + 1 < len(args):
                i += 1
                rename_title = args[i]
            elif not arg.startswith("-"):
                open_files.append(arg)
            i += 1

        win = self.props.active_window
        if not win:
            win = NotesWindow(self, open_files=open_files, create_locked=create_locked)
        else:
            if open_files:
                for f in open_files:
                    win.open_tab_with_file(f)
            elif create_locked:
                win.open_new_tab(create_locked=True)
            elif not insert_text and not rename_title:
                win.open_new_tab()

        if insert_text:
            page = win.get_current_page()
            if page:
                page.clear_ghost_text()
                it = page.buffer.get_iter_at_mark(page.buffer.get_insert())
                content = f"{insert_text}\n" if len(page.get_clean_text().strip()) == 0 else f"\n\n{insert_text}\n"
                page.buffer.insert(it, content)
        if rename_title:
            win.rename_active_document(rename_title)
        if hasattr(win, "trigger_action_progress"):
            win.trigger_action_progress(400)

        win.present()
        return 0


def main():
    app = NotesApplication()
    DEFAULT_NOTES_DIR.mkdir(parents=True, exist_ok=True)
    LOCKED_NOTES_DIR.mkdir(parents=True, exist_ok=True)
    ensure_locked_files_in_locked_dir()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
