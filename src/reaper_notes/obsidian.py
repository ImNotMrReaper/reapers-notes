"""
obsidian.py: Seamless Obsidian Vault Integration for Reaper's Notes.
Provides automatic discovery of vaults created by Obsidian, directory scanning for
.obsidian markers, manual folder selection via file chooser, and Obsidian URI dispatching.
"""

import os
import sys
import json
import urllib.parse
import subprocess
from datetime import datetime
from pathlib import Path

try:
    from .settings import get_setting, set_setting, load_settings, save_settings
except (ImportError, ValueError):
    from settings import get_setting, set_setting, load_settings, save_settings


# Master Obsidian configuration registries across Native, Flatpak, and Snap
OBSIDIAN_REGISTRY_PATHS = [
    Path.home() / ".config" / "obsidian" / "obsidian.json",
    Path.home() / ".var" / "app" / "md.obsidian.Obsidian" / "config" / "obsidian" / "obsidian.json",
    Path.home() / "snap" / "obsidian" / "current" / ".config" / "obsidian" / "obsidian.json",
]

# Common candidate root directories to scan for .obsidian markers
SCAN_ROOT_DIRS = [
    Path.home() / "Documents",
    Path.home() / "Obsidian",
    Path.home() / "Notes",
    Path.home(),
]


def scan_for_obsidian_markers() -> dict[str, str]:
    """
    Scans candidate root directories for folders containing a '.obsidian' marker.
    Obsidian automatically creates a hidden '.obsidian' directory inside every
    folder that was initialized or created as an Obsidian vault.
    Returns {vault_name: vault_path}.
    """
    found_vaults: dict[str, str] = {}

    for root_dir in SCAN_ROOT_DIRS:
        if not root_dir.exists() or not root_dir.is_dir():
            continue

        try:
            # Check the root directory itself
            if (root_dir / ".obsidian").is_dir() and root_dir != Path.home():
                found_vaults[root_dir.name] = str(root_dir)

            # Check direct children (depth 1)
            for child in root_dir.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    if (child / ".obsidian").is_dir():
                        found_vaults[child.name] = str(child)
                    else:
                        # Depth 2 check for nested vaults
                        try:
                            for subchild in child.iterdir():
                                if subchild.is_dir() and not subchild.name.startswith("."):
                                    if (subchild / ".obsidian").is_dir():
                                        found_vaults[subchild.name] = str(subchild)
                        except (PermissionError, OSError):
                            pass
        except (PermissionError, OSError):
            continue

    return found_vaults


def discover_vaults() -> dict[str, str]:
    """
    Discovers all Obsidian vaults configured or created on the system:
    1. Reads Obsidian application registry (obsidian.json) created by Obsidian.
    2. Scans for folders containing the '.obsidian' directory marker.
    3. Merges user-selected custom vaults from settings.
    Returns a mapping of {vault_name: vault_path}.
    """
    vaults: dict[str, str] = {}

    # 1. Check Obsidian's native registries (Native, Flatpak, Snap)
    for reg_path in OBSIDIAN_REGISTRY_PATHS:
        if reg_path.exists():
            try:
                with open(reg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    raw_vaults = data.get("vaults", {})
                    for v_id, v_info in raw_vaults.items():
                        v_path = v_info.get("path")
                        if v_path and os.path.isdir(v_path):
                            v_name = os.path.basename(v_path)
                            vaults[v_name] = v_path
            except Exception:
                pass

    # 2. Check filesystem for folders with .obsidian markers
    marker_vaults = scan_for_obsidian_markers()
    for name, path in marker_vaults.items():
        if name not in vaults:
            vaults[name] = path

    # 3. Check custom vaults saved by the user
    try:
        custom_vaults = get_setting("custom_vaults", [])
        for cv in custom_vaults:
            if os.path.isdir(cv):
                name = os.path.basename(cv)
                if name not in vaults:
                    vaults[name] = cv
    except Exception:
        pass

    return vaults


def discover_vault_details() -> list[dict]:
    """
    Returns rich metadata for all discovered vaults:
    [{"name": ..., "path": ..., "source": "Obsidian App"|".obsidian Marker"|"Custom Folder", "is_active": bool}]
    """
    active_tuple = get_default_vault()
    active_path = active_tuple[1] if active_tuple else None

    registry_paths = set()
    for reg_path in OBSIDIAN_REGISTRY_PATHS:
        if reg_path.exists():
            try:
                with open(reg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for _, v_info in data.get("vaults", {}).items():
                        p = v_info.get("path")
                        if p and os.path.isdir(p):
                            registry_paths.add(p)
            except Exception:
                pass

    marker_vaults = scan_for_obsidian_markers()
    custom_vaults = set(get_setting("custom_vaults", []))

    all_vaults = discover_vaults()
    results = []

    for name, path in all_vaults.items():
        source = "Unknown"
        if path in registry_paths:
            source = "Obsidian App"
        elif path in marker_vaults.values():
            source = ".obsidian Marker"
        elif path in custom_vaults:
            source = "Custom Folder"

        has_obsidian_meta = (Path(path) / ".obsidian").is_dir()

        results.append({
            "name": name,
            "path": path,
            "source": source,
            "has_obsidian_dir": has_obsidian_meta,
            "is_active": (path == active_path)
        })

    return results


def get_default_vault() -> tuple[str, str] | None:
    """
    Returns the primary (vault_name, vault_path) tuple:
    1. Explicit active vault chosen in settings.
    2. Primary vault found in Obsidian registries.
    3. Vault discovered with .obsidian marker.
    4. None if no vault found.
    """
    active_path = get_setting("active_vault_path")
    if active_path and os.path.isdir(active_path):
        return (os.path.basename(active_path), active_path)

    vaults = discover_vaults()
    if not vaults:
        return None

    if "Valut" in vaults:
        return ("Valut", vaults["Valut"])
    first_key = next(iter(vaults))
    return (first_key, vaults[first_key])


def set_active_vault_path(path: str) -> bool:
    """Sets and persists the active Obsidian vault path."""
    if not os.path.isdir(path):
        return False
    set_setting("active_vault_path", path)
    return True


def register_custom_vault(folder_path: str) -> tuple[bool, str]:
    """
    Registers a folder chosen by the user through the file manager as an Obsidian vault.
    If the folder does not have a '.obsidian' directory, initializes one so Obsidian
    recognizes it automatically when opened.
    Returns (success: bool, message: str).
    """
    p = Path(folder_path).resolve()
    if not p.exists():
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return False, f"Could not create directory: {e}"

    if not p.is_dir():
        return False, f"Path is not a directory: {folder_path}"

    obsidian_dir = p / ".obsidian"
    if not obsidian_dir.exists():
        try:
            obsidian_dir.mkdir(parents=True, exist_ok=True)
            with open(obsidian_dir / "app.json", "w", encoding="utf-8") as f:
                json.dump({"legacyEditor": False}, f)
        except Exception as e:
            print(f"[Obsidian] Warning: Could not initialize .obsidian marker: {e}")

    try:
        custom_vaults = get_setting("custom_vaults", [])
        str_path = str(p)
        if str_path not in custom_vaults:
            custom_vaults.append(str_path)
            set_setting("custom_vaults", custom_vaults)
        set_active_vault_path(str_path)
        return True, f"Vault '{p.name}' registered and set as active."
    except Exception as e:
        return False, f"Error updating settings: {e}"


def has_frontmatter(content: str) -> bool:
    """Checks whether the markdown string already starts with a complete YAML frontmatter block."""
    stripped = content.lstrip()
    if not stripped.startswith("---"):
        return False
    lines = stripped.splitlines()
    if len(lines) < 2:
        return False
    for line in lines[1:]:
        if line.strip() == "---":
            return True
    return False


def generate_frontmatter(title: str, tags: list[str] = None) -> str:
    """Generates standard, clean YAML frontmatter for Obsidian."""
    clean_title = title.strip() or "Untitled Note"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    tag_list = tags or ["notes"]
    tag_lines = "\n".join(f"  - {t}" for t in tag_list)
    return f"""---
title: "{clean_title}"
date: {now_str}
tags:
{tag_lines}
---"""


def create_obsidian_template(title: str) -> str:
    """Generates an elegant, structured Obsidian Markdown document with YAML frontmatter."""
    clean_title = title.strip() or "Untitled Note"
    fm = generate_frontmatter(clean_title)
    return f"""{fm}

# {clean_title}

"""


def extract_note_title(content: str, fallback_title: str = "") -> str:
    """Extracts a clean, safe note title from YAML frontmatter, Markdown H1 headers, or fallback."""
    clean = fallback_title.strip()
    if clean.endswith(".txt") or clean.endswith(".md"):
        clean = Path(clean).stem

    if clean and not clean.startswith("Untitled") and any(c.isalnum() for c in clean):
        return clean

    in_frontmatter = False
    for line in content.splitlines():
        line_s = line.strip()
        if line_s.startswith("---"):
            if not in_frontmatter:
                in_frontmatter = True
                continue
            else:
                in_frontmatter = False
                break
        if in_frontmatter and line_s.startswith("title:"):
            cand = line_s.split("title:", 1)[1].strip().strip("\"'").strip()
            if cand and any(c.isalnum() for c in cand):
                return cand

    for line in content.splitlines():
        line_s = line.strip()
        if line_s.startswith("# "):
            cand = line_s[2:].strip()
            if cand and any(c.isalnum() for c in cand):
                return cand

    for line in content.splitlines():
        line_s = line.strip()
        if line_s and not line_s.startswith("---") and any(c.isalnum() for c in line_s):
            words = line_s.split()[:6]
            cand = " ".join(words)
            if cand and any(c.isalnum() for c in cand):
                return cand

    return f"Note_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}"


def sanitize_filename(name: str) -> str:
    """Ensures filename contains valid characters and at least one alphanumeric character."""
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    if not safe or not any(c.isalnum() for c in safe):
        safe = f"Note_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return safe


def push_to_obsidian(content: str, title: str = "", vault_path: str = None) -> tuple[bool, str]:
    """
    Saves the content into the specified Obsidian vault and opens it in Obsidian.
    Returns (success: bool, message_or_filepath: str).
    """
    import shutil
    if not vault_path:
        default_vault = get_default_vault()
        if not default_vault:
            fallback_dir = Path.home() / "Documents" / "Obsidian Vault"
            register_custom_vault(str(fallback_dir))
            vault_path = str(fallback_dir)
        else:
            vault_path = default_vault[1]

    vault_dir = Path(vault_path)
    if not vault_dir.exists():
        try:
            vault_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return False, f"Failed to create vault directory: {e}"

    # Ensure .obsidian marker exists so Obsidian sees this folder as a vault
    obsidian_marker = vault_dir / ".obsidian"
    if not obsidian_marker.exists():
        try:
            obsidian_marker.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    raw_title = extract_note_title(content, title)
    safe_title = sanitize_filename(raw_title)

    # Format content with frontmatter and title cleanly
    if not has_frontmatter(content):
        fm = generate_frontmatter(safe_title)
        content_stripped = content.strip()

        has_h1 = any(line.strip().startswith("# ") for line in content_stripped.splitlines())
        if not has_h1 and content_stripped:
            content = f"{fm}\n\n# {safe_title}\n\n{content_stripped}\n"
        elif has_h1:
            content = f"{fm}\n\n{content_stripped}\n"
        else:
            content = f"{fm}\n\n# {safe_title}\n\n"
    else:
        content = content.strip() + "\n"

    target_file = vault_dir / f"{safe_title}.md"
    if safe_title.startswith("Note_") or "Untitled" in title:
        counter = 1
        while target_file.exists():
            target_file = vault_dir / f"{safe_title} ({counter}).md"
            counter += 1

    try:
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        return False, f"Error saving note: {e}"

    try:
        # Use absolute path for robust resolution across all Obsidian packaging variants
        encoded_path = urllib.parse.quote(str(target_file.resolve()))
        uri = f"obsidian://open?path={encoded_path}"
        
        # Native, non-blocking desktop URI launch via GIO / Wayland
        try:
            import gi
            gi.require_version("Gio", "2.0")
            from gi.repository import Gio
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except Exception:
            subprocess.Popen(["xdg-open", uri], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception as e:
        print(f"Failed to launch Obsidian: {e}", file=sys.stderr)

    return True, str(target_file)
