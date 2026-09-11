# Reaper's Notes & Text Editor

<p align="center">
  <img src="assets/icons/hicolor/128x128/apps/com.reaper.Notes.png" alt="Reaper's Notes Icon" width="96" height="96">
</p>

<p align="center">
  <strong>Universal GTK4 / Libadwaita text editor and encrypted notes application for Linux.</strong><br>
  Multi-tab document editing, 176+ language syntax highlighting, real-time local CPU voice dictation, and military-grade AES-256-GCM biometric locked notes.
</p>

<p align="center">
  <a href="#installation"><img src="https://img.shields.io/badge/package-.deb%20%7C%20install.sh-purple.svg" alt="Package"></a>
  <a href="#biometric-encryption"><img src="https://img.shields.io/badge/security-AES--256--GCM-green.svg" alt="Security"></a>
  <a href="#local-whisper-voice-dictation"><img src="https://img.shields.io/badge/voice-Whisper%20CPU%20(Offline)-blue.svg" alt="Voice"></a>
  <a href="#license"><img src="https://img.shields.io/badge/license-MIT-orange.svg" alt="License"></a>
</p>

---

## Overview

**Reaper's Notes** is a modern desktop text editor and encrypted vault engineered to seamlessly replace standard desktop text editors (like GNOME Text Editor and Gedit) while providing high-performance features for daily writing, coding, and private note-taking:

1. **Full Text Editor Engine:** Multi-tab editing (`Adw.TabView`), Find and Replace (`Ctrl+F` / `Ctrl+H`), zoom controls (`Ctrl++` / `Ctrl+-`), line numbers, margin guides, and word wrap.
2. **Interactive Language & File Type Selector:** Click the bottom-right language tag to choose from 176+ syntax highlighters or switch instantly to **Plain Text** (stripping all markdown headers and numbered list formatting for pure text editing).
3. **Biometric Vault & AES-256-GCM Encryption:** A dynamic HeaderBar button shows a lock icon (`🔒`) on unlocked notes and an unlock icon (`🔓`) on locked notes. Encrypted with AES-256-GCM and guarded by GNOME Tri-Factor Biometrics (Howdy Face ID, Goodix fingerprint, or PAM fallback).
4. **Real-Time Streaming Voice Dictation:** Local in-memory C++ engine (`libwhisper_easy.so`) streaming spoken words directly onto the canvas in real time with ~50-70ms latency. Zero cloud dependencies. Press `Escape` anytime to abort without altering your note.
5. **Safe Antigravity AI Assistant:** Dedicated modal prompt dialog (`Ctrl+Alt+A`) to summarize, outline, or transform text on demand.
6. **Adaptive System Theme & OLED Pitch Black:** Seamlessly adapts to your GNOME system theme (Light, Dark, and user accent colors) by default, with an Appearance menu to toggle Pure OLED Pitch Black (`#000000`), Dark Mode, or Light Mode.

---

## Features

### 1. Interactive Language Selector & Plain Text Mode
- Click the language badge in the bottom-right statusbar (`Markdown ▾`, `Plain Text ▾`, `Python ▾`, etc.).
- A searchable popover provides instant access to **176+ syntax highlighters** supported by GtkSourceView 5.
- Switching to **Plain Text** immediately removes all markdown styling, headings, and list formatting, allowing the editor to function as a traditional clean text editor.
- Automatically adjusts default save extensions (`.txt`, `.md`, `.py`, `.c`, `.rs`, `.json`, etc.).

### 2. Tri-Factor Biometric Encryption (AES-256-GCM)
- **Dynamic Lock/Unlock Button:**
  - On unencrypted notes: Displays a lock icon (`changes-prevent-symbolic`) with tooltip *"Lock & Encrypt Note (AES-256-GCM)"*.
  - On locked notes: Displays an unlock icon (`changes-allow-symbolic`) with tooltip *"Unlock Note (Biometric authorization required)"*.
- **Cryptographic Security:** Every locked note is encrypted using authenticated AES-256-GCM with a unique 12-byte random initialization vector (IV/nonce) and machine-salted key derivation (PBKDF2-HMAC-SHA256).
- **Authentication Tri-Factor:** Native Polkit integration triggers Howdy Facial Recognition, Goodix capacitive fingerprint scanner, or password fallback.

### 3. Real-Time Streaming Voice Dictation (Local Whisper CPU)
- Speak naturally and watch words appear live at your cursor as you speak.
- Powered by a lightweight in-memory C++ wrapper (`libwhisper_easy.so`) communicating directly with `libwhisper.so`.
- Runs 100% on your local CPU (sub-70ms inference on modern Intel/AMD processors). Zero telemetry or network requests.
- **Escape Key Abort:** Hit `Escape` anytime during recording to immediately drop uncommitted speech audio and keep your note clean.

### 4. Obsidian Vault Integration
- **Direct Vault Discovery:** Automatically detects configured Obsidian vaults from `~/.config/obsidian/obsidian.json` and standard directories (`~/Documents/Valut`, `~/Documents/Obsidian Vault`).
- **Push to Obsidian (`Ctrl+Alt+O`):** Save your active document straight into your Obsidian vault with a single keypress or HeaderBar click (`document-send-symbolic`). Dispatches native `obsidian://open` URIs so your note is instantly indexed.
- **New Obsidian Note (`Ctrl+Shift+O`):** Spawns a new tab pre-populated with standard Obsidian YAML frontmatter (`title`, `date`, `tags: [notes]`) and Markdown syntax.

### 5. Modular Plugin System & Universal AI Backend
- **Plugin Architecture:** Decoupled extensions engine (`src/reaper_notes/plugins/`) featuring:
  - `base.py`: Clean lifecycle interface (`on_load`, `on_unload`, `get_menu_items`).
  - `manager.py`: Dynamic runtime discovery across built-in plugins and user scripts (`~/.config/reaper-notes/plugins/`).
  - `example_plugin.py`: Reference implementation providing live document word/character counters, ISO timestamp insertion, and text transformations.
- **AI-Agnostic Engine (`ai_plugin.py`):** External users on GitHub are never locked into a single AI runtime. Supports:
  - **Antigravity CLI** (`agy`)
  - **Anthropic Claude CLI** (`claude`)
  - **Ollama Local Daemon** (offline private LLMs at `http://localhost:11434`)
  - **OpenAI-Compatible API** endpoints
  - Auto-detection selects the best available local or system AI tool automatically.

### 6. Adaptive Appearance & OLED Pitch Black
- **System Default:** Automatically tracks your GNOME desktop light/dark theme and system accent colors.
- **Pure OLED Pitch Black (Reaper):** Pure `#000000` canvas with Ubuntu Purple (`#7764D8`) accents for deep battery savings and zero backlight bleed on OLED displays.
- **Dark Mode & Light Mode:** Force standard dark or light schemes regardless of system settings.

---

## Installation

### Method 1: Debian / Ubuntu `.deb` Package (Recommended)

Download the latest `.deb` package from the [Releases](https://github.com/ImNotMrReaper/reapers-notes/releases) tab or build it locally:

```bash
# Install package
sudo dpkg -i reapers-notes_1.0.0_amd64.deb

# Resolve any missing system libraries
sudo apt-get install -f
```

### Method 2: Universal 1-Line Installer

```bash
curl -fsSL https://raw.githubusercontent.com/ImNotMrReaper/reapers-notes/main/install.sh | bash
```

### Method 3: Manual Clone & Install

```bash
git clone https://github.com/ImNotMrReaper/reapers-notes.git
cd reapers-notes

# System-wide install (all users):
sudo ./install.sh

# Or local user install (without root):
./install.sh
```

---

## Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `Ctrl + T` / `Ctrl + N` | Open New Tab |
| `Ctrl + Shift + N` | Open New Window |
| `Ctrl + W` | Close Active Tab |
| `Ctrl + O` | Open Document / Note |
| `Ctrl + S` | Save Document |
| `Ctrl + Shift + S` | Save Document As... |
| `Ctrl + F` | Find in Document |
| `Ctrl + H` | Find and Replace |
| `Ctrl + Alt + O` | Push Note to Obsidian Vault |
| `Ctrl + Shift + O` | Create New Obsidian Note |
| `Ctrl + Alt + V` / `F9` | Start / Stop Real-Time Voice Dictation |
| `Escape` | Cancel Voice Dictation / Close Search Bar |
| `Ctrl + Alt + A` | AI Assistant Prompt Dialog |
| `Tab` / `Right Arrow` | Accept Ghost-Text Autocomplete Suggestion |
| `Ctrl + +` / `Ctrl + =` | Zoom In |
| `Ctrl + -` | Zoom Out |
| `Ctrl + 0` | Reset Zoom to 100% |

---

## Building the Debian Package

To package the application from source:

```bash
cd reapers-notes
./build_deb.sh
```

This generates `reapers-notes_1.1.0_amd64.deb` in the repository root.

---

## Uninstallation

To cleanly remove Reaper's Notes while preserving your saved notes:

```bash
# If installed via .deb:
sudo apt remove reapers-notes

# If installed via install.sh:
./uninstall.sh
```

---

## License

This project is licensed under the [MIT License](LICENSE).
