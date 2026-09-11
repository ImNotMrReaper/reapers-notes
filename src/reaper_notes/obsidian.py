"""
obsidian.py: Seamless Obsidian Vault Integration for Reaper's Notes.
Provides automatic discovery of vaults created by Obsidian, directory scanning for
.obsidian markers, manual folder selection via file chooser, and Obsidian URI dispatching.
"""

import os
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


def create_obsidian_template(title: str) -> str:
    """Generates standard Obsidian Markdown with YAML frontmatter."""
    clean_title = title.strip() or "Untitled Note"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""---
title: {clean_title}
date: {now_str}
tags:
  - notes
---

# {clean_title}

"""


def push_to_obsidian(content: str, title: str = "", vault_path: str = None) -> tuple[bool, str]:
    """
    Saves the content into the specified Obsidian vault.
    Returns (success: bool, message_or_filepath: str).
    """
    if not vault_path:
        default_vault = get_default_vault()
        if not default_vault:
            return False, "No Obsidian vault found on this system."
        vault_path = default_vault[1]

    vault_dir = Path(vault_path)
    if not vault_dir.exists():
        try:
            vault_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return False, f"Failed to create vault directory: {e}"

    clean_title = title.strip()
    if not clean_title:
        for line in content.splitlines():
            line_s = line.strip()
            if line_s.startswith("# "):
                clean_title = line_s[2:].strip()
                break
        if not clean_title:
            clean_title = f"Note {datetime.now().strftime('%Y-%m-%d %H%M%S')}"

    safe_title = "".join(c for c in clean_title if c.isalnum() or c in (" ", "-", "_")).strip()
    if not safe_title:
        safe_title = f"Note_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    target_file = vault_dir / f"{safe_title}.md"
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
        vault_name = vault_dir.name
        rel_path = target_file.name
        encoded_vault = urllib.parse.quote(vault_name)
        encoded_file = urllib.parse.quote(rel_path)
        uri = f"obsidian://open?vault={encoded_vault}&file={encoded_file}"
        subprocess.Popen(["xdg-open", uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    return True, str(target_file)
