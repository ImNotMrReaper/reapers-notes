"""
ai_plugin.py: Universal Multi-Backend AI Assistant Plugin for Reaper's Notes.
Supports Antigravity CLI (agy), Claude CLI (claude), Ollama (Local LLM), and OpenAI-compatible endpoints.
Ensures external users on GitHub are never locked into a single AI runtime.
"""

import os
import shutil
import json
import urllib.request
import urllib.error
import subprocess
import threading
from typing import Callable, Any
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from .base import NotesPlugin
try:
    from ..settings import get_setting, set_setting
except (ImportError, ValueError):
    from settings import get_setting, set_setting


class AIAssistantPlugin(NotesPlugin):
    id = "ai_assistant"
    name = "AI Assistant (Universal)"
    description = "Smart in-editor AI completions supporting Antigravity, Claude CLI, Ollama (Local), & OpenAI."
    version = "1.1.0"
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
            ("Run AI Prompt... (Ctrl+Alt+A)", lambda: self.prompt_dialog(window)),
            ("Configure AI Provider...", lambda: self.config_dialog(window)),
        ]

    def get_active_provider(self) -> str:
        """Returns the configured AI provider, auto-detecting best available backend."""
        saved = get_setting("ai_provider", "auto")
        if saved != "auto":
            return saved

        # Auto-detection hierarchy:
        if shutil.which("agy"):
            return "antigravity"
        elif shutil.which("claude"):
            return "claude"
        elif self._check_ollama_alive():
            return "ollama"
        elif shutil.which("ollama"):
            return "ollama"
        return "antigravity"

    def _check_ollama_alive(self) -> bool:
        """Quick ping to check if local Ollama daemon is running."""
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def prompt_dialog(self, window: Any):
        """Shows the AI Prompt dialog."""
        dialog = Adw.MessageDialog(
            transient_for=window,
            heading="AI Assistant Prompt",
            body="Enter your prompt or instruction for document completion:",
        )
        entry = Gtk.Entry()
        entry.set_placeholder_text("e.g., Summarize this document, write meeting notes, create unit tests...")
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

        page = window.get_current_page()
        file_title = page.filepath if page and page.filepath else (page.title if page and page.title else "Untitled Note")

        def on_response(dlg, response):
            if response == "generate":
                prompt_text = entry.get_text().strip()
                if not prompt_text:
                    window.set_status_message("⚠️ Prompt cannot be empty.")
                    dlg.close()
                    return
                provider = self.get_active_provider()
                window.btn_ai.add_css_class("ai-btn-thinking")
                window.set_status_message(f"🤖 AI ({provider.capitalize()}) thinking: \"{prompt_text[:30]}...\"")
                self.dispatch_prompt(prompt_text, file_title, lambda res: self._on_ai_completed(window, res))
            else:
                window.set_status_message("AI prompt canceled.")
            dlg.close()

        dialog.connect("response", on_response)
        entry.connect("activate", lambda _: dialog.response("generate"))
        dialog.present()

    def _on_ai_completed(self, window: Any, response: str):
        window.btn_ai.remove_css_class("ai-btn-thinking")
        page = window.get_current_page()
        if not page:
            return

        if response:
            page.clear_ghost_text()
            it = page.buffer.get_iter_at_mark(page.buffer.get_insert())
            insert_text = f"\n\n{response}\n"
            page.buffer.insert(it, insert_text)
            window.set_status_message(f"✅ AI response inserted ({len(response)} chars)!")
        else:
            window.set_status_message("⚠️ AI returned an empty response.")

    def dispatch_prompt(self, prompt: str, file_title: str, on_complete_cb: Callable[[str], None]):
        """Executes prompt against the configured provider asynchronously."""
        provider = self.get_active_provider()

        import sys
        print(f"\n--- [Reaper's Notes AI Prompt Execution] ---", flush=True)
        print(f"Current File: {file_title}", flush=True)
        print(f"Prompt: {prompt}\n", flush=True)

        contextual_prompt = f"[Current File: {file_title}]\n{prompt}"

        def worker():
            if not prompt or not prompt.strip():
                GLib.idle_add(on_complete_cb, "")
                return

            result = ""
            try:
                if provider == "antigravity":
                    result = self._call_antigravity(contextual_prompt)
                elif provider == "claude":
                    result = self._call_claude(contextual_prompt)
                elif provider == "ollama":
                    result = self._call_ollama(contextual_prompt)
                elif provider == "openai":
                    result = self._call_openai(contextual_prompt)
                else:
                    # Default fallback to Antigravity
                    result = self._call_antigravity(contextual_prompt)
            except Exception as e:
                result = f"[{provider.capitalize()} Error]: {e}"

            print(f"--- [AI Execution Result] ---\n{result}\n---------------------------------------------\n", flush=True)
            GLib.idle_add(on_complete_cb, result)

        threading.Thread(target=worker, daemon=True).start()

    def _call_antigravity(self, prompt: str) -> str:
        if not shutil.which("agy"):
            return "[Error]: Antigravity CLI ('agy') not found in PATH. Please install or switch provider."
        cmd = ["agy", "-p", prompt.strip(), "--output-format", "text"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        output = res.stdout.strip()
        if not output and res.stderr:
            return f"[Antigravity Error]: {res.stderr.strip()}"
        return output

    def _call_claude(self, prompt: str) -> str:
        if not shutil.which("claude"):
            return "[Error]: Claude CLI ('claude') not found in PATH."
        cmd = ["claude", "-p", prompt.strip()]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        return res.stdout.strip() or f"[Claude Error]: {res.stderr.strip()}"

    def _call_ollama(self, prompt: str) -> str:
        model = get_setting("ai_model", "llama3")
        endpoint = get_setting("ai_endpoint", "http://localhost:11434/api/generate")
        payload = json.dumps({
            "model": model,
            "prompt": prompt.strip(),
            "stream": False
        }).encode("utf-8")
        req = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "").strip()

    def _call_openai(self, prompt: str) -> str:
        api_key = os.environ.get("OPENAI_API_KEY") or get_setting("openai_api_key", "")
        if not api_key:
            return "[Error]: No OpenAI API key configured. Set OPENAI_API_KEY environment variable."
        model = get_setting("ai_model", "gpt-4o-mini")
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt.strip()}],
            "temperature": 0.7
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()

    def config_dialog(self, window: Any):
        """Displays settings dialog to select AI provider and models."""
        dialog = Adw.MessageDialog(
            transient_for=window,
            heading="Configure AI Provider",
            body="Select the AI backend for document generation and prompts:",
        )
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(16)
        box.set_margin_end(16)

        # Provider Selector
        lbl_p = Gtk.Label(label="Provider:")
        lbl_p.set_xalign(0)
        box.append(lbl_p)

        providers = [
            ("auto", "Auto-Detect Best Available"),
            ("antigravity", "Antigravity CLI (agy)"),
            ("claude", "Anthropic Claude CLI"),
            ("ollama", "Ollama Local Daemon (localhost:11434)"),
            ("openai", "OpenAI API"),
        ]
        dropdown = Gtk.DropDown.new_from_strings([p[1] for p in providers])
        current_p = get_setting("ai_provider", "auto")
        for idx, (p_id, _) in enumerate(providers):
            if p_id == current_p:
                dropdown.set_selected(idx)
                break
        box.append(dropdown)

        # Model entry
        lbl_m = Gtk.Label(label="Model (for Ollama / OpenAI):")
        lbl_m.set_xalign(0)
        box.append(lbl_m)
        model_entry = Gtk.Entry()
        model_entry.set_text(get_setting("ai_model", "llama3"))
        box.append(model_entry)

        dialog.set_extra_child(box)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")

        def on_response(dlg, response):
            if response == "save":
                sel_idx = dropdown.get_selected()
                sel_provider = providers[sel_idx][0]
                set_setting("ai_provider", sel_provider)
                set_setting("ai_model", model_entry.get_text().strip())
                window.set_status_message(f"⚙️ AI Provider configured: {providers[sel_idx][1]}")

        dialog.connect("response", on_response)
        dialog.present()
