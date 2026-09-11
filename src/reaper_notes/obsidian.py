"""
obsidian.py: Seamless Obsidian Vault Integration for Reaper's Notes.
Provides automatic vault discovery, Markdown note pushing, and Obsidian URI dispatching.
"""

import os
import json
import urllib.parse
import subprocess
from datetime import datetime
from pathlib import Path


OBSIDIAN_CONFIG_PATH = Path.home() / ".config" / "obsidian" / "obsidian.json"
FALLBACK_VAULT_PATHS = [
    Path.home() / "Documents" / "Valut",
    Path.home() / "Documents" / "Obsidian Vault",
    Path.home() / "Obsidian",
]


def discover_vaults() -> dict[str, str]:
    """
    Discovers Obsidian vaults configured on the system.
    Returns a mapping of {vault_name: vault_path}.
    """
    vaults: dict[str, str] = {}

    if OBSIDIAN_CONFIG_PATH.exists():
        try:
            with open(OBSIDIAN_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                raw_vaults = data.get("vaults", {})
                for v_id, v_info in raw_vaults.items():
                    v_path = v_info.get("path")
                    if v_path and os.path.isdir(v_path):
                        v_name = os.path.basename(v_path)
                        vaults[v_name] = v_path
        except Exception:
            pass

    # Check fallback paths if not found
    for fallback in FALLBACK_VAULT_PATHS:
        if fallback.exists() and fallback.is_dir():
            name = fallback.name
            if name not in vaults:
                vaults[name] = str(fallback)

    return vaults


def get_default_vault() -> tuple[str, str] | None:
    """Returns the primary (vault_name, vault_path) tuple or None if no vault exists."""
    vaults = discover_vaults()
    if not vaults:
        return None
    # Prefer 'Valut' if present, otherwise first available
    if "Valut" in vaults:
        return ("Valut", vaults["Valut"])
    first_key = next(iter(vaults))
    return (first_key, vaults[first_key])


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
        # Extract first heading from content if available
        for line in content.splitlines():
            line_s = line.strip()
            if line_s.startswith("# "):
                clean_title = line_s[2:].strip()
                break
        if not clean_title:
            clean_title = f"Note {datetime.now().strftime('%Y-%m-%d %H%M%S')}"

    # Sanitize title for filename
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

    # Attempt to trigger Obsidian URI
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
