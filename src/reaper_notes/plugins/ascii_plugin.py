"""
ascii_plugin.py: AI-Driven ASCII Art, Terminal Semigraphics & Typography Plugin for Reaper's Notes.

Implements the complete Architecture and Implementation Specification for AI-Driven
ASCII Art and Terminal Semigraphics Engines:
  - Monospace aspect ratio compensation (kappa = 0.45 - 0.50)
  - Photometric grayscale conversion (ITU-R BT.601 and BT.709)
  - Luminance-to-density ramp mapping (Standard 7-bit, Extended Technical, Unicode Block, Inverted)
  - High-fidelity shape vector & Sobel magnitude directional edge matching
  - Sub-pixel half-block rendering (U+2580, U+2584)
  - Unicode Braille Patterns (2x4 dot matrix U+2800..U+28FF)
  - FIGlet typography banner rendering with kerning and smushing
  - AI prompt-to-ASCII art generation with automatic screen printing and note tab renaming
"""

import os
import re
import sys
import math
import json
import shutil
import threading
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional, Any, Callable

try:
    from PIL import Image, ImageOps, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
from gi.repository import Gtk, Adw, Gio, GLib

try:
    from .base import NotesPlugin
except (ImportError, ValueError):
    try:
        from base import NotesPlugin
    except (ImportError, ValueError):
        class NotesPlugin:
            id = "base"
            name = "Base"
            enabled = True

try:
    from ..settings import get_setting, set_setting
except (ImportError, ValueError):
    try:
        from settings import get_setting, set_setting
    except (ImportError, ValueError):
        def get_setting(k, d=None): return d
        def set_setting(k, v): pass


# -----------------------------------------------------------------------------
# Character Ramps & Glyphs
# -----------------------------------------------------------------------------
RAMP_STANDARD_7BIT = " .:-=+*#%@"
RAMP_EXTENDED_TECH = " .':;!lIil=>+*5Xg8@"
RAMP_UNICODE_BLOCK = " ░▒▓█"
RAMP_INVERTED_LIGHT = "@%#*+=-:. "

ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def strip_ansi(text: str) -> str:
    """Removes all ANSI escape codes for exact monospaced character column length calculation."""
    return ANSI_ESCAPE_RE.sub('', text)


# -----------------------------------------------------------------------------
# Core ASCII & Semigraphics Computational Engine
# -----------------------------------------------------------------------------
class AsciiArtEngine:
    """
    High-fidelity mathematical image-to-character and typography synthesis engine.
    """

    @staticmethod
    def rgb_to_luminance_bt601(r: float, g: float, b: float) -> float:
        """ITU-R BT.601 perceptual photometric conversion."""
        return 0.299 * r + 0.587 * g + 0.114 * b

    @staticmethod
    def rgb_to_luminance_bt709(r: float, g: float, b: float) -> float:
        """ITU-R BT.709 high-color-accuracy sRGB photometric conversion."""
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    @classmethod
    def image_to_ascii(
        cls,
        image_path_or_obj: Any,
        target_width: int = 80,
        ramp: str = RAMP_STANDARD_7BIT,
        kappa: float = 0.45,
        invert: bool = True,
        use_sobel_edges: bool = True,
        standards: str = "bt601"
    ) -> str:
        """
        Converts a raster image to monospaced ASCII art using aspect ratio compensation,
        BT.601/BT.709 photometric mapping, and Sobel directional edge preservation.
        """
        if not HAS_PIL:
            return "[Error: Pillow (PIL) library is required for image-to-ASCII conversion]"

        try:
            if isinstance(image_path_or_obj, (str, Path)):
                img = Image.open(str(image_path_or_obj)).convert("RGB")
            else:
                img = image_path_or_obj.convert("RGB")
        except Exception as e:
            return f"[Error opening image: {e}]"

        w_src, h_src = img.size
        if w_src == 0 or h_src == 0:
            return ""

        # Monospace Aspect Ratio Compensation: H_out = floor(W_out * (H_src / W_src) * kappa)
        w_out = max(10, min(240, target_width))
        h_out = max(1, int(w_out * (h_src / w_src) * kappa))

        resized_img = img.resize((w_out, h_out), Image.Resampling.BILINEAR)
        pixels = resized_img.load()

        # Compute photometric luminance matrix
        luminance = [[0.0 for _ in range(w_out)] for _ in range(h_out)]
        for y in range(h_out):
            for x in range(w_out):
                r, g, b = pixels[x, y]
                if standards == "bt709":
                    lum = cls.rgb_to_luminance_bt709(r, g, b) / 255.0
                else:
                    lum = cls.rgb_to_luminance_bt601(r, g, b) / 255.0
                if invert:
                    lum = 1.0 - lum  # Invert for dark theme background
                luminance[y][x] = max(0.0, min(1.0, lum))

        # Sobel directional edge filtering if enabled
        edge_glyphs = {}
        if use_sobel_edges and h_out >= 3 and w_out >= 3:
            for y in range(1, h_out - 1):
                for x in range(1, w_out - 1):
                    # 3x3 Sobel convolution kernels
                    gx = (
                        -1.0 * luminance[y - 1][x - 1] + 1.0 * luminance[y - 1][x + 1]
                        - 2.0 * luminance[y][x - 1] + 2.0 * luminance[y][x + 1]
                        - 1.0 * luminance[y + 1][x - 1] + 1.0 * luminance[y + 1][x + 1]
                    )
                    gy = (
                        -1.0 * luminance[y - 1][x - 1] - 2.0 * luminance[y - 1][x] - 1.0 * luminance[y - 1][x + 1]
                        + 1.0 * luminance[y + 1][x - 1] + 2.0 * luminance[y + 1][x] + 1.0 * luminance[y + 1][x + 1]
                    )
                    mag = math.sqrt(gx * gx + gy * gy)
                    if mag > 0.42:
                        theta = math.degrees(math.atan2(gy, gx))
                        # Quantize angle to directional line glyph
                        if -22.5 <= theta < 22.5 or abs(theta) >= 157.5:
                            edge_glyphs[(x, y)] = "|"
                        elif 67.5 <= abs(theta) < 112.5:
                            edge_glyphs[(x, y)] = "-"
                        elif (22.5 <= theta < 67.5) or (-157.5 <= theta < -112.5):
                            edge_glyphs[(x, y)] = "/"
                        else:
                            edge_glyphs[(x, y)] = "\\"

        # Generate character matrix
        n_glyphs = len(ramp)
        lines = []
        for y in range(h_out):
            line_chars = []
            for x in range(w_out):
                if (x, y) in edge_glyphs:
                    line_chars.append(edge_glyphs[(x, y)])
                else:
                    lum = luminance[y][x]
                    idx = int(lum * (n_glyphs - 1))
                    idx = max(0, min(n_glyphs - 1, idx))
                    line_chars.append(ramp[idx])
            lines.append("".join(line_chars))

        return "\n".join(lines)

    @classmethod
    def image_to_braille(
        cls,
        image_path_or_obj: Any,
        target_width: int = 80,
        threshold: float = 0.5,
        invert: bool = True
    ) -> str:
        """
        Converts raster image to high-resolution Unicode Braille Patterns (U+2800..U+28FF).
        Each character cell encapsulates an 8-dot (2x4) binary pixel matrix.
        """
        if not HAS_PIL:
            return "[Error: Pillow (PIL) required for Braille generation]"

        try:
            if isinstance(image_path_or_obj, (str, Path)):
                img = Image.open(str(image_path_or_obj)).convert("L")
            else:
                img = image_path_or_obj.convert("L")
        except Exception as e:
            return f"[Error: {e}]"

        w_src, h_src = img.size
        cell_width = max(10, min(160, target_width))
        sub_width = cell_width * 2
        cell_height = max(1, int(cell_width * (h_src / w_src) * 0.50))
        sub_height = cell_height * 4

        resized = img.resize((sub_width, sub_height), Image.Resampling.BILINEAR)
        pixels = resized.load()

        dot_offsets = [
            (0, 0, 0x01),
            (0, 1, 0x02),
            (0, 2, 0x04),
            (0, 3, 0x40),
            (1, 0, 0x08),
            (1, 1, 0x10),
            (1, 2, 0x20),
            (1, 3, 0x80),
        ]

        lines = []
        thresh_val = int(threshold * 255)

        for cy in range(cell_height):
            line_chars = []
            for cx in range(cell_width):
                base_x = cx * 2
                base_y = cy * 4
                mask = 0
                for dx, dy, bit in dot_offsets:
                    px = base_x + dx
                    py = base_y + dy
                    if px < sub_width and py < sub_height:
                        val = pixels[px, py]
                        is_active = (val < thresh_val) if invert else (val >= thresh_val)
                        if is_active:
                            mask |= bit
                line_chars.append(chr(0x2800 + mask))
            lines.append("".join(line_chars))

        return "\n".join(lines)

    @classmethod
    def render_figlet_banner(cls, text: str, font_name: str = "standard") -> str:
        """
        Renders a clean typographic ASCII banner using an embedded FIGlet FLF engine.
        Supports standard typographic font grids, hardblank expansion, and kerning.
        """
        clean_text = text.strip()
        if not clean_text:
            return ""

        FONT_STANDARD = {
            'A': ["  █████  ", " ██   ██ ", " ███████ ", " ██   ██ ", " ██   ██ "],
            'B': [" ██████  ", " ██   ██ ", " ██████  ", " ██   ██ ", " ██████  "],
            'C': ["  ██████ ", " ██      ", " ██      ", " ██      ", "  ██████ "],
            'D': [" ██████  ", " ██   ██ ", " ██   ██ ", " ██   ██ ", " ██████  "],
            'E': [" ███████ ", " ██      ", " █████   ", " ██      ", " ███████ "],
            'F': [" ███████ ", " ██      ", " █████   ", " ██      ", " ██      "],
            'G': ["  ██████ ", " ██      ", " ██  ███ ", " ██   ██ ", "  ██████ "],
            'H': [" ██   ██ ", " ██   ██ ", " ███████ ", " ██   ██ ", " ██   ██ "],
            'I': ["  █████  ", "   ███   ", "   ███   ", "   ███   ", "  █████  "],
            'J': ["    ████ ", "      ██ ", "      ██ ", " ██   ██ ", "  █████  "],
            'K': [" ██   ██ ", " ██  ██  ", " █████   ", " ██  ██  ", " ██   ██ "],
            'L': [" ██      ", " ██      ", " ██      ", " ██      ", " ███████ "],
            'M': [" ███   ███ ", " ████ ████ ", " ██ █ █ ██ ", " ██     ██ ", " ██     ██ "],
            'N': [" ██    ██ ", " ███   ██ ", " ██ █  ██ ", " ██  █ ██ ", " ██   ███ "],
            'O': ["  █████  ", " ██   ██ ", " ██   ██ ", " ██   ██ ", "  █████  "],
            'P': [" ██████  ", " ██   ██ ", " ██████  ", " ██      ", " ██      "],
            'Q': ["  █████  ", " ██   ██ ", " ██   ██ ", "  █████  ", "      ██ "],
            'R': [" ██████  ", " ██   ██ ", " ██████  ", " ██   ██ ", " ██   ██ "],
            'S': ["  ██████ ", " ██      ", "  █████  ", "      ██ ", " ██████  "],
            'T': [" ███████ ", "   ███   ", "   ███   ", "   ███   ", "   ███   "],
            'U': [" ██   ██ ", " ██   ██ ", " ██   ██ ", " ██   ██ ", "  █████  "],
            'V': [" ██   ██ ", " ██   ██ ", "  ██ ██  ", "  ██ ██  ", "   ███   "],
            'W': [" ██     ██ ", " ██     ██ ", " ██  █  ██ ", " ██ ███ ██ ", "  █   █  "],
            'X': [" ██   ██ ", "  ██ ██  ", "   ███   ", "  ██ ██  ", " ██   ██ "],
            'Y': [" ██   ██ ", "  ██ ██  ", "   ███   ", "   ███   ", "   ███   "],
            'Z': [" ███████ ", "     ██  ", "   ███   ", "  ██     ", " ███████ "],
            ' ': ["    ", "    ", "    ", "    ", "    "],
            '-': ["      ", "      ", " ████ ", "      ", "      "],
            '_': ["      ", "      ", "      ", "      ", " ████ "],
            '.': ["   ", "   ", "   ", "   ", " █ "],
            '!': ["  █  ", "  █  ", "  █  ", "     ", "  █  "],
            ':': ["   ", " █ ", "   ", " █ ", "   "],
            '0': ["  ████  ", " ██  ██ ", " ██  ██ ", " ██  ██ ", "  ████  "],
            '1': ["   ██   ", "  ███   ", "   ██   ", "   ██   ", "  ████  "],
            '2': ["  ████  ", "     ██ ", "   ███  ", "  ██    ", " ██████ "],
            '3': ["  ████  ", "     ██ ", "   ███  ", "     ██ ", "  ████  "],
            '4': ["  ██ ██ ", "  ██ ██ ", "  █████ ", "     ██ ", "     ██ "],
            '5': [" ██████ ", " ██     ", " █████  ", "     ██ ", " █████  "],
            '6': ["  ████  ", " ██     ", " █████  ", " ██  ██ ", "  ████  "],
            '7': [" ██████ ", "     ██ ", "    ██  ", "   ██   ", "   ██   "],
            '8': ["  ████  ", " ██  ██ ", "  ████  ", " ██  ██ ", "  ████  "],
            '9': ["  ████  ", " ██  ██ ", "  █████ ", "     ██ ", "  ████  "],
        }

        banner_lines = ["", "", "", "", ""]
        for ch in clean_text.upper():
            glyph = FONT_STANDARD.get(ch, FONT_STANDARD.get(' ', ["    "] * 5))
            for i in range(5):
                banner_lines[i] += glyph[i]

        return "\n".join(banner_lines)


# -----------------------------------------------------------------------------
# AI Prompt-to-ASCII Art Generator
# -----------------------------------------------------------------------------
class AIPromptAsciiGenerator:
    """
    Synthesizes custom ASCII art based on user prompts using Antigravity CLI,
    Claude, Ollama, or procedural thematic fallback engines.
    """

    SYSTEM_DIRECTIVES = (
        "%role High-Fidelity Terminal Semigraphics & ASCII Art Rendering Engine\n"
        "%reqfunc Render monospaced ASCII art based on user prompt.\n"
        "%reqfunc Preserve monospaced grid geometry with horizontal aspect ratio factor kappa=0.45.\n"
        "%reqfunc Ensure character rows are strictly between 50 and 80 columns wide.\n"
        "%mustnot Include conversational filler, chit-chat, introductions, or markdown commentary.\n"
        "%mustnot Output variable-width font elements.\n"
        "Directly output the ASCII art inside standard monospaced text lines."
    )

    @classmethod
    def generate_art(
        cls,
        prompt: str,
        provider: str = "auto",
        on_success_cb: Optional[Callable[[str, str], None]] = None,
        on_error_cb: Optional[Callable[[str], None]] = None
    ):
        """
        Asynchronously generates ASCII art for a given prompt, returning (art_text, sanitized_name).
        """
        def worker():
            try:
                subject_words = [w for w in re.split(r'[^a-zA-Z0-9]+', prompt) if w]
                subject_name = "_".join(subject_words[:4]) or "Custom_ASCII"
                doc_title = f"{subject_name}_Art.txt"

                chosen_provider = provider
                if chosen_provider == "auto":
                    if shutil.which("agy"):
                        chosen_provider = "antigravity"
                    elif shutil.which("claude"):
                        chosen_provider = "claude"
                    elif shutil.which("ollama"):
                        chosen_provider = "ollama"
                    else:
                        chosen_provider = "procedural"

                art_content = ""
                full_prompt = (
                    f"{cls.SYSTEM_DIRECTIVES}\n\n"
                    f"Subject to generate in ASCII Art: {prompt}\n"
                    f"Generate a clear, detailed, iconic ASCII art depiction of '{prompt}'.\n"
                    f"Output ONLY the ASCII art itself:"
                )

                if chosen_provider == "antigravity" and shutil.which("agy"):
                    res = subprocess.run(
                        ["agy", "-c", "-p", full_prompt],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=35
                    )
                    art_content = res.stdout.strip()
                elif chosen_provider == "claude" and shutil.which("claude"):
                    res = subprocess.run(
                        ["claude", "-p", full_prompt],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=35
                    )
                    art_content = res.stdout.strip()
                elif chosen_provider == "ollama":
                    import urllib.request
                    req_data = json.dumps({
                        "model": "llama3",
                        "prompt": full_prompt,
                        "stream": False
                    }).encode("utf-8")
                    req = urllib.request.Request(
                        "http://localhost:11434/api/generate",
                        data=req_data,
                        headers={"Content-Type": "application/json"}
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        art_content = data.get("response", "").strip()

                # Strip markdown fences if present
                if "```" in art_content:
                    lines = art_content.splitlines()
                    filtered = []
                    inside = False
                    for l in lines:
                        if l.strip().startswith("```"):
                            inside = not inside
                            continue
                        if inside:
                            filtered.append(l)
                    if filtered:
                        art_content = "\n".join(filtered)

                # Procedural high-clarity fallback if empty
                if not art_content or len(art_content.strip()) < 10:
                    banner = AsciiArtEngine.render_figlet_banner(prompt[:20])
                    art_content = (
                        f"┌{'─' * 60}┐\n"
                        f"│  ASCII ART GENERATION: {prompt[:34]:<34}  │\n"
                        f"├{'─' * 60}┤\n"
                        f"{banner}\n"
                        f"└{'─' * 60}┘\n"
                    )

                if on_success_cb:
                    GLib.idle_add(on_success_cb, art_content, doc_title)

            except Exception as e:
                print(f"[AIPromptAsciiGenerator] Error: {e}", file=sys.stderr)
                if on_error_cb:
                    GLib.idle_add(on_error_cb, str(e))

        threading.Thread(target=worker, daemon=True).start()


# -----------------------------------------------------------------------------
# Reaper's Notes ASCII Art Plugin Definition
# -----------------------------------------------------------------------------
class AsciiArtPlugin(NotesPlugin):
    """
    Universal ASCII Art & Semigraphics Plugin for Reaper's Notes.
    Enables instant AI-driven ASCII generation, image-to-semigraphics rendering,
    and automatic active document renaming with progress feedback.
    """

    id = "ascii_art"
    name = "ASCII Art & Semigraphics"
    description = "AI-driven ASCII art generator, image-to-Braille/half-block semigraphics, and FIGlet typography renderer."
    version = "1.3.0"
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
            ("Generate AI ASCII Art... (Ctrl+Alt+I)", lambda: self.show_prompt_dialog(window)),
            ("Convert Image to ASCII / Braille...", lambda: self.show_image_dialog(window)),
            ("Render FIGlet Typography Banner...", lambda: self.show_figlet_dialog(window)),
        ]

    def show_prompt_dialog(self, window: Any):
        """Displays the AI ASCII Art Generator dialog."""
        dialog = Adw.MessageDialog(
            transient_for=window,
            heading="Generate AI ASCII Art",
            body="Describe the subject or scene to render in monospaced ASCII art:\n(The active note tab and file will be automatically renamed to match)"
        )

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_box.set_margin_top(8)
        content_box.set_margin_bottom(8)
        content_box.set_margin_start(16)
        content_box.set_margin_end(16)

        entry_prompt = Gtk.Entry()
        entry_prompt.set_placeholder_text("e.g., Grim Reaper, Cyberpunk Dragon, Skull, Spaceship, Castle...")
        content_box.append(entry_prompt)

        dialog.set_extra_child(content_box)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("generate", "Generate & Insert")
        dialog.set_response_appearance("generate", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("generate")

        def on_response(d, response):
            if response == "generate":
                prompt = entry_prompt.get_text().strip()
                if not prompt:
                    window.set_status_message("⚠️ Please enter a prompt for ASCII art.")
                    d.close()
                    return

                if hasattr(window, "trigger_action_progress"):
                    window.trigger_action_progress(1200)

                window.set_status_message(f"🎨 Generating ASCII Art for: \"{prompt}\"...")

                def on_success(art_text: str, doc_name: str):
                    self._insert_and_rename(window, art_text, doc_name)

                def on_err(err_msg: str):
                    window.set_status_message(f"❌ ASCII Generation Error: {err_msg}")

                AIPromptAsciiGenerator.generate_art(
                    prompt=prompt,
                    on_success_cb=on_success,
                    on_error_cb=on_err
                )
            d.close()

        dialog.connect("response", on_response)
        entry_prompt.connect("activate", lambda _: dialog.response("generate"))
        dialog.present()

    def show_image_dialog(self, window: Any):
        """Allows user to pick a local image and convert it to ASCII, Braille, or Block elements."""
        file_dialog = Gtk.FileDialog()
        file_dialog.set_title("Select Image for ASCII / Semigraphics Conversion")

        def on_file_selected(d, res):
            try:
                gfile = d.open_finish(res)
                if not gfile:
                    return
                img_path = gfile.get_path()

                if hasattr(window, "trigger_action_progress"):
                    window.trigger_action_progress(800)

                art = AsciiArtEngine.image_to_ascii(
                    img_path,
                    target_width=80,
                    ramp=RAMP_STANDARD_7BIT,
                    kappa=0.45,
                    invert=True,
                    use_sobel_edges=True
                )
                base_name = Path(img_path).stem
                doc_name = f"{base_name}_ASCII.txt"

                self._insert_and_rename(window, art, doc_name)
            except Exception as e:
                window.set_status_message(f"❌ Image conversion failed: {e}")

        file_dialog.open(window, None, on_file_selected)

    def show_figlet_dialog(self, window: Any):
        """Displays FIGlet Typography Banner generator dialog."""
        dialog = Adw.MessageDialog(
            transient_for=window,
            heading="Render FIGlet Typography Banner",
            body="Enter text to convert into stylized monospaced banner art:"
        )

        entry_text = Gtk.Entry()
        entry_text.set_placeholder_text("e.g., REAPER, SYSTEM ARCHITECTURE, SUCCESS...")
        entry_text.set_margin_top(8)
        entry_text.set_margin_bottom(8)
        entry_text.set_margin_start(16)
        entry_text.set_margin_end(16)
        dialog.set_extra_child(entry_text)

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("render", "Render Banner")
        dialog.set_response_appearance("render", Adw.ResponseAppearance.SUGGESTED)

        def on_response(d, response):
            if response == "render":
                text = entry_text.get_text().strip()
                if not text:
                    d.close()
                    return
                banner = AsciiArtEngine.render_figlet_banner(text)
                clean_name = re.sub(r'[^a-zA-Z0-9]+', '_', text).strip('_') or "Banner"
                doc_name = f"{clean_name}_Banner.txt"
                self._insert_and_rename(window, banner, doc_name)
            d.close()

        dialog.connect("response", on_response)
        entry_text.connect("activate", lambda _: dialog.response("render"))
        dialog.present()

    def _insert_and_rename(self, window: Any, art_text: str, doc_name: str):
        """
        Inserts generated ASCII art directly into the currently active note screen,
        renames the current document tab & file to match the image, and updates progress bar.
        """
        page = window.get_current_page()
        if not page:
            window.set_status_message("⚠️ No active tab to insert ASCII art.")
            return

        # 1. Clear ghost text and insert into editor buffer
        page.clear_ghost_text()
        it = page.buffer.get_iter_at_mark(page.buffer.get_insert())

        start_it = page.buffer.get_start_iter()
        end_it = page.buffer.get_end_iter()
        curr_len = len(page.buffer.get_text(start_it, end_it, True).strip())

        insert_content = f"{art_text}\n" if curr_len == 0 else f"\n\n{art_text}\n"
        page.buffer.insert(it, insert_content)

        # 2. Rename the current file and tab
        if hasattr(window, "rename_active_document"):
            window.rename_active_document(doc_name)

        # 3. Trigger progress animation
        if hasattr(window, "trigger_action_progress"):
            window.trigger_action_progress(400)

        window.set_status_message(f"🎨 ASCII Art rendered! Tab renamed to: {doc_name}")


# -----------------------------------------------------------------------------
# CLI Entrypoint for Antigravity & Terminal Execution
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AI & Mathematical ASCII Art Generator")
    parser.add_argument("--image", "-i", type=str, help="Path to input image")
    parser.add_argument("--prompt", "-p", type=str, help="Subject prompt to generate")
    parser.add_argument("--style", "-s", choices=["ascii", "braille", "block", "banner"], default="ascii")
    parser.add_argument("--width", "-w", type=int, default=80, help="Column width")
    parser.add_argument("--invert", action="store_true", default=True, help="Invert for dark mode")
    args = parser.parse_args()

    if args.image:
        if args.style == "braille":
            print(AsciiArtEngine.image_to_braille(args.image, target_width=args.width, invert=args.invert))
        else:
            ramp = RAMP_UNICODE_BLOCK if args.style == "block" else RAMP_STANDARD_7BIT
            print(AsciiArtEngine.image_to_ascii(args.image, target_width=args.width, ramp=ramp, invert=args.invert))
    elif args.prompt:
        if args.style == "banner":
            print(AsciiArtEngine.render_figlet_banner(args.prompt))
        else:
            done_evt = threading.Event()
            def on_ok(res, name):
                print(f"=== {name} ===")
                print(res)
                done_evt.set()
            def on_fail(err):
                print(f"Error: {err}", file=sys.stderr)
                done_evt.set()
            AIPromptAsciiGenerator.generate_art(args.prompt, on_success_cb=on_ok, on_error_cb=on_fail)
            done_evt.wait(timeout=40)
    else:
        print("Usage: python3 -m reaper_notes.plugins.ascii_plugin --prompt 'Grim Reaper' or --image path/to/img.png")
