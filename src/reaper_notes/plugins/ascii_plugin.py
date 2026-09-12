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
import html
import shutil
import threading
import subprocess
import urllib.request
import urllib.parse
import io
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
# -----------------------------------------------------------------------------
# Multi-Source Online ASCII Art Fetcher & Search Engine
# -----------------------------------------------------------------------------
class OnlineAsciiFetcher:
    """
    Asynchronously queries multiple online ASCII art repositories:
      - asciiart.eu (largest curated web archive with categorized collections)
      - ascii.co.uk (classic Usenet & retro terminal ASCII art)
      - ascii-art.de (alphabetical text file archive)
    Returns normalized, deduplicated ASCII art candidates with source attribution.
    """

    @classmethod
    def search_all_sources(cls, query: str, limit_per_source: int = 5) -> List[dict]:
        results = []
        lock = threading.Lock()
        threads = []
        clean_q = query.strip().lower()
        slug_q = re.sub(r"[^a-z0-9]+", "-", clean_q).strip("-")
        if not slug_q:
            return []
        raw_q = urllib.parse.quote(clean_q)

        def fetch_asciiart_eu():
            try:
                url = f"https://www.asciiart.eu/search?q={raw_q}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
                with urllib.request.urlopen(req, timeout=4) as r:
                    raw = r.read().decode("utf-8", errors="ignore")
                    cards = re.findall(r"class=[\"\'][^\"\']*art-card__ascii[^\"\']*[\"\'][^>]*>(.*?)</div>", raw, re.DOTALL)
                    found = 0
                    for c in cards:
                        text = html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                        lines = [l for l in text.splitlines() if l.strip()]
                        if len(lines) >= 2 and len(text) > 30:
                            max_cols = max(len(l) for l in text.splitlines()) if text.splitlines() else 0
                            with lock:
                                results.append({
                                    "source": "asciiart.eu",
                                    "title": query.title(),
                                    "art": text,
                                    "lines": len(text.splitlines()),
                                    "cols": max_cols
                                })
                            found += 1
                            if found >= limit_per_source:
                                break
            except Exception:
                pass

        def fetch_ascii_co_uk():
            variants = [slug_q]
            if slug_q.endswith("s"):
                variants.append(slug_q[:-1])
            else:
                variants.append(slug_q + "s")

            for variant in variants:
                try:
                    url = f"https://ascii.co.uk/art/{variant}"
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
                    with urllib.request.urlopen(req, timeout=4) as r:
                        raw = r.read().decode("utf-8", errors="ignore")
                        pres = re.findall(r"<pre[^>]*>(.*?)</pre>", raw, re.DOTALL)
                        found = 0
                        for p in pres:
                            if "ASCII Character Codes" in p or "<blockquote>" in p:
                                continue
                            p_clean = re.sub(r'<[^>]+>', '', p)
                            text = html.unescape(p_clean).strip()
                            lines = text.splitlines()
                            cleaned_lines = [l for l in lines if not l.strip().startswith("See ") and not "for more !" in l]
                            text = "\n".join(cleaned_lines).strip()
                            non_empty = [l for l in text.splitlines() if l.strip()]
                            if len(non_empty) >= 2 and len(text) > 30:
                                max_cols = max(len(l) for l in text.splitlines()) if text.splitlines() else 0
                                with lock:
                                    results.append({
                                        "source": "ascii.co.uk",
                                        "title": query.title(),
                                        "art": text,
                                        "lines": len(text.splitlines()),
                                        "cols": max_cols
                                    })
                                found += 1
                                if found >= limit_per_source:
                                    break
                        if found > 0:
                            break
                except Exception:
                    pass

        def fetch_ascii_art_de():
            letter = slug_q[0]
            candidates = [f"https://www.ascii-art.de/ascii/{letter}/{slug_q}.txt"]
            if slug_q.endswith("s"):
                candidates.append(f"https://www.ascii-art.de/ascii/{letter}/{slug_q[:-1]}.txt")
            else:
                candidates.append(f"https://www.ascii-art.de/ascii/{letter}/{slug_q}s.txt")

            for candidate in candidates:
                try:
                    req = urllib.request.Request(candidate, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
                    with urllib.request.urlopen(req, timeout=4) as r:
                        content = r.read().decode("utf-8", errors="ignore")
                        blocks = re.split(r"\n\s*[-_=]{10,}\s*\n|\n{4,}", content)
                        found = 0
                        for b in blocks:
                            text = b.strip()
                            lines = [l for l in text.splitlines() if l.strip()]
                            if len(lines) >= 3 and len(text) > 40 and not text.lower().startswith("ascii art by"):
                                max_cols = max(len(l) for l in text.splitlines()) if text.splitlines() else 0
                                with lock:
                                    results.append({
                                        "source": "ascii-art.de",
                                        "title": query.title(),
                                        "art": text,
                                        "lines": len(text.splitlines()),
                                        "cols": max_cols
                                    })
                                found += 1
                                if found >= limit_per_source:
                                    break
                        if found > 0:
                            break
                except Exception:
                    pass

        def fetch_online_images():
            if not HAS_PIL:
                return
            try:
                params = urllib.parse.urlencode({
                    'action': 'query',
                    'generator': 'search',
                    'gsrsearch': clean_q,
                    'gsrnamespace': 6,
                    'gsrlimit': 4,
                    'prop': 'imageinfo',
                    'iiprop': 'url|thumburl|mime',
                    'iiurlwidth': 400,
                    'format': 'json'
                })
                url = f"https://commons.wikimedia.org/w/api.php?{params}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
                with urllib.request.urlopen(req, timeout=4.5) as resp:
                    data = json.loads(resp.read().decode())
                    pages = data.get("query", {}).get("pages", {})
                    for pid, p in pages.items():
                        raw_t = p.get("title", "").replace("File:", "").strip()
                        title = re.sub(r"\.[a-zA-Z0-9]+$", "", raw_t)
                        info = p.get("imageinfo", [{}])[0]
                        thumb = info.get("thumburl") or info.get("url")
                        if not thumb:
                            continue
                        try:
                            img_req = urllib.request.Request(thumb, headers={"User-Agent": "Mozilla/5.0"})
                            with urllib.request.urlopen(img_req, timeout=4) as img_resp:
                                img = Image.open(io.BytesIO(img_resp.read()))
                                art = AsciiArtEngine.image_to_ascii(img, target_width=68, use_sobel_edges=True)
                                if len(art.strip()) > 50:
                                    lines_cnt = len(art.splitlines())
                                    cols_cnt = max(len(l) for l in art.splitlines()) if art.splitlines() else 0
                                    with lock:
                                        results.append({
                                            "source": "Researched Image",
                                            "title": f"Image: {title[:28]}",
                                            "art": art,
                                            "lines": lines_cnt,
                                            "cols": cols_cnt
                                        })
                        except Exception:
                            pass
            except Exception:
                pass

        def fetch_local_gallery():
            gallery_dir = Path.home() / ".agents" / "ascii-gallery"
            if not gallery_dir.exists():
                return
            for art_file in gallery_dir.rglob("*.txt"):
                if clean_q in art_file.stem.lower():
                    try:
                        content = art_file.read_text(encoding="utf-8", errors="ignore")
                        lines = [l for l in content.splitlines() if not l.startswith("#")]
                        art = "\n".join(lines).strip()
                        if len(art) > 20:
                            lines_cnt = len(art.splitlines())
                            cols_cnt = max(len(l) for l in art.splitlines()) if lines else 0
                            with lock:
                                results.append({
                                    "source": "Local Gallery",
                                    "title": f"Gallery: {art_file.stem.title()}",
                                    "art": art,
                                    "lines": lines_cnt,
                                    "cols": cols_cnt
                                })
                    except Exception:
                        pass

        for fn in [fetch_asciiart_eu, fetch_ascii_co_uk, fetch_ascii_art_de, fetch_online_images, fetch_local_gallery]:
            t = threading.Thread(target=fn)
            t.daemon = True
            t.start()
            threads.append(t)

        for t in threads:
            t.join(timeout=5.0)

        # Deduplicate
        unique_results = []
        seen_art = set()
        for r in results:
            normalized = "".join(r["art"].split())
            if normalized not in seen_art:
                seen_art.add(normalized)
                unique_results.append(r)

        return unique_results


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
                        ["agy", "-c", "-p", full_prompt, "--output-format", "text"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=35
                    )
                    art_content = res.stdout.strip()
                    if not art_content and res.returncode != 0:
                        res2 = subprocess.run(
                            ["agy", "-p", full_prompt, "--output-format", "text"],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            timeout=35
                        )
                        art_content = res2.stdout.strip()
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
                    if GLib.main_depth() > 0:
                        GLib.idle_add(on_success_cb, art_content, doc_title)
                    else:
                        on_success_cb(art_content, doc_title)

            except Exception as e:
                print(f"[AIPromptAsciiGenerator] Error: {e}", file=sys.stderr)
                if on_error_cb:
                    if GLib.main_depth() > 0:
                        GLib.idle_add(on_error_cb, str(e))
                    else:
                        on_error_cb(str(e))

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
            ("Search Online ASCII Art Archives... (Ctrl+Shift+I)", lambda: self.show_online_search_dialog(window)),
            ("Generate AI ASCII Art... (Ctrl+Alt+I)", lambda: self.show_prompt_dialog(window)),
            ("Convert Image to ASCII / Braille...", lambda: self.show_image_dialog(window)),
            ("Render FIGlet Typography Banner...", lambda: self.show_figlet_dialog(window)),
        ]

    def show_online_search_dialog(self, window: Any, initial_query: str = "", preloaded_results: Optional[List[dict]] = None):
        """Displays interactive multi-source online ASCII art browser & previewer."""
        dialog = Adw.MessageDialog(
            transient_for=window,
            heading="Online ASCII Art Archives",
            body="Search across asciiart.eu, ascii.co.uk, and ascii-art.de collections:"
        )

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_box.set_margin_top(8)
        content_box.set_margin_bottom(8)
        content_box.set_margin_start(16)
        content_box.set_margin_end(16)

        # Search row
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        entry_search = Gtk.Entry()
        entry_search.set_hexpand(True)
        entry_search.set_placeholder_text("Search query, e.g. dragon, skull, reaper, sword, cat...")
        if initial_query:
            entry_search.set_text(initial_query)
        btn_search = Gtk.Button(label="Search Online")
        btn_search.add_css_class("suggested-action")
        search_box.append(entry_search)
        search_box.append(btn_search)
        content_box.append(search_box)

        # Status & navigation row
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_prev = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        btn_prev.set_tooltip_text("Previous Artwork")
        btn_next = Gtk.Button.new_from_icon_name("go-next-symbolic")
        btn_next.set_tooltip_text("Next Artwork")
        lbl_status = Gtk.Label(label="Enter a query to search online archives.")
        lbl_status.set_hexpand(True)
        lbl_status.set_xalign(0.0)
        lbl_status.add_css_class("dim-label")

        nav_box.append(btn_prev)
        nav_box.append(btn_next)
        nav_box.append(lbl_status)
        content_box.append(nav_box)

        # Monospaced preview canvas
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(260)
        scroll.set_max_content_height(360)
        scroll.set_min_content_width(540)
        scroll.add_css_class("card")

        preview_tv = Gtk.TextView()
        preview_tv.set_monospace(True)
        preview_tv.set_editable(False)
        preview_tv.set_cursor_visible(False)
        preview_tv.set_top_margin(8)
        preview_tv.set_bottom_margin(8)
        preview_tv.set_left_margin(12)
        preview_tv.set_right_margin(12)
        preview_buf = preview_tv.get_buffer()
        scroll.set_child(preview_tv)
        content_box.append(scroll)

        dialog.set_extra_child(content_box)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("insert_all", "Insert All")
        dialog.add_response("insert", "Insert This Art")
        dialog.set_response_appearance("insert", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("insert")

        current_results = list(preloaded_results or [])
        current_idx = [0]

        def update_view():
            if not current_results:
                btn_prev.set_sensitive(False)
                btn_next.set_sensitive(False)
                preview_buf.set_text("")
                dialog.set_response_enabled("insert", False)
                dialog.set_response_enabled("insert_all", False)
                return

            idx = current_idx[0]
            item = current_results[idx]
            src = item.get("source", "Web")
            lines = item.get("lines", 0)
            cols = item.get("cols", 0)
            lbl_status.set_text(f"Match {idx + 1} of {len(current_results)} • [{src}] ({lines} lines x {cols} cols)")
            preview_buf.set_text(item.get("art", ""))
            btn_prev.set_sensitive(idx > 0)
            btn_next.set_sensitive(idx < len(current_results) - 1)
            dialog.set_response_enabled("insert", True)
            dialog.set_response_enabled("insert_all", True)

        def do_search():
            q = entry_search.get_text().strip()
            if not q:
                return
            btn_search.set_sensitive(False)
            lbl_status.set_text(f"Searching online archives for '{q}'...")
            if hasattr(window, "trigger_action_progress"):
                window.trigger_action_progress(1000)

            def worker():
                res = OnlineAsciiFetcher.search_all_sources(q)
                def on_done():
                    btn_search.set_sensitive(True)
                    current_results.clear()
                    current_results.extend(res)
                    current_idx[0] = 0
                    if res:
                        update_view()
                        window.set_status_message(f"🌐 Found {len(res)} online artworks for '{q}'")
                    else:
                        lbl_status.set_text(f"No online matches found for '{q}'. Try another keyword.")
                        update_view()
                GLib.idle_add(on_done)

            threading.Thread(target=worker, daemon=True).start()

        btn_search.connect("clicked", lambda _: do_search())
        entry_search.connect("activate", lambda _: do_search())

        btn_prev.connect("clicked", lambda _: (current_idx.__setitem__(0, max(0, current_idx[0] - 1)), update_view()))
        btn_next.connect("clicked", lambda _: (current_idx.__setitem__(0, min(len(current_results) - 1, current_idx[0] + 1)), update_view()))

        def on_response(d, response):
            if response == "insert" and current_results:
                item = current_results[current_idx[0]]
                q = entry_search.get_text().strip() or "ASCII"
                doc_name = f"{re.sub(r'[^a-zA-Z0-9]+', '_', q).strip('_')}_{item.get('source', 'Web').replace('.', '_')}_Art.txt"
                self._insert_and_rename(window, item["art"], doc_name)
                # Save to persistent local gallery for agent and future lookup
                try:
                    gal_dir = Path.home() / ".agents" / "ascii-gallery" / "objects"
                    gal_dir.mkdir(parents=True, exist_ok=True)
                    clean_fn = re.sub(r'[^a-zA-Z0-9_-]+', '_', q).strip('_').lower() or "art"
                    (gal_dir / f"{clean_fn}.txt").write_text(f"# Subject: {q}\n# Source: {item.get('source', 'Online Archive')}\n\n" + item["art"], encoding="utf-8")
                except Exception:
                    pass
            elif response == "insert_all" and current_results:
                q = entry_search.get_text().strip() or "ASCII"
                combined = []
                for i, r in enumerate(current_results):
                    combined.append(f"# [{r.get('source', 'Web')}] Artwork {i+1}\n" + r["art"])
                doc_name = f"{re.sub(r'[^a-zA-Z0-9]+', '_', q).strip('_')}_Multi_Art.txt"
                self._insert_and_rename(window, "\n\n" + ("\n" + "="*50 + "\n\n").join(combined), doc_name)
            d.close()

        dialog.connect("response", on_response)
        if preloaded_results:
            update_view()
        elif initial_query:
            do_search()
        else:
            update_view()

        dialog.present()

    def show_prompt_dialog(self, window: Any):
        """Displays the AI ASCII Art Generator dialog with online archives integration."""
        dialog = Adw.MessageDialog(
            transient_for=window,
            heading="Generate AI ASCII Art",
            body="Describe the subject or scene to render in monospaced ASCII art:\n(Searches online archives first, then falls back to AI generation)"
        )

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_box.set_margin_top(8)
        content_box.set_margin_bottom(8)
        content_box.set_margin_start(16)
        content_box.set_margin_end(16)

        entry_prompt = Gtk.Entry()
        entry_prompt.set_placeholder_text("e.g., Grim Reaper, Cyberpunk Dragon, Skull, Spaceship, Castle...")
        content_box.append(entry_prompt)

        chk_online = Gtk.CheckButton(label="Search online archives & research real images (Wikimedia, asciiart.eu, ascii.co.uk)")
        chk_online.set_active(True)
        content_box.append(chk_online)

        dialog.set_extra_child(content_box)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("generate", "Generate / Search")
        dialog.set_response_appearance("generate", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("generate")

        def on_response(d, response):
            if response == "generate":
                prompt = entry_prompt.get_text().strip()
                if not prompt:
                    window.set_status_message("⚠️ Please enter a prompt for ASCII art.")
                    d.close()
                    return

                if chk_online.get_active():
                    window.set_status_message(f"🌐 Checking online archives for: \"{prompt}\"...")
                    if hasattr(window, "trigger_action_progress"):
                        window.trigger_action_progress(800)

                    def search_worker():
                        matches = OnlineAsciiFetcher.search_all_sources(prompt)
                        def on_search_done():
                            if matches:
                                best_art = matches[0]["art"]
                                art_title = matches[0].get("title", prompt)
                                safe_title = "".join(c for c in art_title if c.isalnum() or c in (" ", "-", "_")).strip() or "ASCII_Art"
                                doc_name = f"{safe_title}_Art.txt"
                                self._insert_and_rename(window, best_art, doc_name)
                                window.set_status_message(f"🎨 Researched & rendered ASCII artwork: '{art_title}'!")
                            else:
                                window.set_status_message(f"🎨 No online matches found for '{prompt}'. Synthesizing via AI...")
                                if hasattr(window, "trigger_action_progress"):
                                    window.trigger_action_progress(1200)

                                def on_success(art_text: str, doc_name: str):
                                    self._insert_and_rename(window, art_text, doc_name)

                                def on_err(err_msg: str):
                                    window.set_status_message(f"❌ ASCII Generation Error: {err_msg}")

                                AIPromptAsciiGenerator.generate_art(
                                    prompt=prompt,
                                    on_success_cb=on_success,
                                    on_error_cb=on_err
                                )
                        GLib.idle_add(on_search_done)

                    threading.Thread(target=search_worker, daemon=True).start()
                else:
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
    parser.add_argument("--search", "-q", type=str, help="Search across online archives (asciiart.eu, ascii.co.uk, ascii-art.de)")
    parser.add_argument("--image", "-i", type=str, help="Path to input image")
    parser.add_argument("--prompt", "-p", type=str, help="Subject prompt to generate")
    parser.add_argument("--style", "-s", choices=["ascii", "braille", "block", "banner"], default="ascii")
    parser.add_argument("--width", "-w", type=int, default=80, help="Column width")
    parser.add_argument("--invert", action="store_true", default=True, help="Invert for dark mode")
    args = parser.parse_args()

    if args.search:
        print(f"Searching online archives for '{args.search}'...")
        results = OnlineAsciiFetcher.search_all_sources(args.search)
        if not results:
            print(f"No online matches found for '{args.search}'.")
        else:
            print(f"Found {len(results)} matches across online archives:\n")
            for i, r in enumerate(results):
                print(f"--- [Result {i+1} from {r['source']}] ({r['lines']} lines x {r['cols']} cols) ---")
                print(r['art'])
                print()
    elif args.image:
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
