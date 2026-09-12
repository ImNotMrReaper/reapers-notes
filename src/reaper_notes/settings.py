"""
settings.py: User configuration & theme persistence for Reaper's Notes.
"""

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "reaper-notes"
SETTINGS_FILE = CONFIG_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "theme_mode": "system",  # "system", "oled", "dark", "light"
    "font_size": 13,
    "line_numbers": False,
    "highlight_current_line": False,
    "word_wrap": True,
    "right_margin": False,
    "default_language": "markdown",
    "active_vault_path": None,
    "custom_vaults": []
}


def load_settings() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.exists():
        save_settings(DEFAULT_SETTINGS)
        return dict(DEFAULT_SETTINGS)

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            merged = dict(DEFAULT_SETTINGS)
            merged.update(data)
            return merged
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(data: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[Settings] Error saving: {e}")


def get_setting(key: str, default=None):
    settings = load_settings()
    return settings.get(key, default)


def set_setting(key: str, value):
    settings = load_settings()
    settings[key] = value
    save_settings(settings)
