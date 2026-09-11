"""
ai_assistant.py: Direct Antigravity CLI integration for in-editor prompt execution.
"""

import sys
import subprocess
import threading
from gi.repository import GLib


def dispatch_antigravity_prompt(prompt: str, on_complete_cb):
    """
    Executes prompt against Antigravity CLI in a background thread.
    Calls on_complete_cb(response_text: str) on the GTK main loop.
    """
    def worker():
        if not prompt or not prompt.strip():
            GLib.idle_add(on_complete_cb, "")
            return

        cmd = ["agy", "-p", prompt.strip(), "--output-format", "text"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            output = res.stdout.strip()
            if not output and res.stderr:
                output = f"[Antigravity Error]: {res.stderr.strip()}"
            GLib.idle_add(on_complete_cb, output)
        except subprocess.TimeoutExpired:
            GLib.idle_add(on_complete_cb, "[Antigravity Error]: Request timed out after 90s.")
        except Exception as e:
            GLib.idle_add(on_complete_cb, f"[Antigravity Error]: {e}")

    threading.Thread(target=worker, daemon=True).start()
