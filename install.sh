#!/usr/bin/env bash
# ==============================================================================
# Reaper's Notes: Universal Linux Installer
# Supports Debian, Ubuntu, Linux Mint, Pop!_OS, and other modern distributions.
# Can run with sudo (system-wide) or as standard user (local user install).
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "======================================================================"
echo "          Installing Reaper's Notes (Modern Text Editor)             "
echo "======================================================================"

# Determine installation scope
if [ "$(id -u)" -eq 0 ]; then
    INSTALL_PREFIX="/usr"
    APP_DIR="/usr/share/reapers-notes"
    BIN_DIR="/usr/bin"
    DESKTOP_DIR="/usr/share/applications"
    ICON_DIR="/usr/share/icons/hicolor"
    IS_SYSTEM=1
    echo ">>> Target Scope: System-Wide (${INSTALL_PREFIX})"
else
    INSTALL_PREFIX="${HOME}/.local"
    APP_DIR="${HOME}/.local/share/reapers-notes"
    BIN_DIR="${HOME}/.local/bin"
    DESKTOP_DIR="${HOME}/.local/share/applications"
    ICON_DIR="${HOME}/.local/share/icons/hicolor"
    IS_SYSTEM=0
    echo ">>> Target Scope: Local User (${INSTALL_PREFIX})"
fi

# 1. Install System Dependencies if apt is available
if command -v apt-get >/dev/null 2>&1; then
    echo ">>> Checking and installing system dependencies (APT)..."
    DEPS="python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gtksource-5 python3-cryptography libpipewire-0.3-0 zenity"
    if [ "$IS_SYSTEM" -eq 1 ]; then
        apt-get update -qq || true
        apt-get install -y -qq $DEPS || true
    elif command -v sudo >/dev/null 2>&1; then
        echo ">>> Requesting sudo access to verify system GTK4 / Libadwaita libraries..."
        sudo apt-get update -qq || true
        sudo apt-get install -y -qq $DEPS || true
    fi
fi

# 2. Create Target Directories
mkdir -p "${APP_DIR}/styles"
mkdir -p "${BIN_DIR}"
mkdir -p "${DESKTOP_DIR}"

# 3. Copy Application Code
echo ">>> Installing application core files into ${APP_DIR}..."
cp "${SCRIPT_DIR}/src/reaper_notes/"*.py "${APP_DIR}/"
cp "${SCRIPT_DIR}/src/reaper_notes/"*.css "${APP_DIR}/"
if [ -f "${SCRIPT_DIR}/src/reaper_notes/libwhisper_easy.so" ]; then
    cp "${SCRIPT_DIR}/src/reaper_notes/libwhisper_easy.so" "${APP_DIR}/"
fi
if [ -d "${SCRIPT_DIR}/src/reaper_notes/styles" ]; then
    cp "${SCRIPT_DIR}/src/reaper_notes/styles/"*.xml "${APP_DIR}/styles/" 2>/dev/null || true
fi

chmod 755 "${APP_DIR}"/*.py
chmod 644 "${APP_DIR}"/*.css 2>/dev/null || true

# 4. Install Executable Launcher
echo ">>> Installing launcher into ${BIN_DIR}/reaper-notes..."
cat << EOF_BIN > "${BIN_DIR}/reaper-notes"
#!/usr/bin/env bash
exec python3 "${APP_DIR}/main.py" "\$@"
EOF_BIN
chmod 755 "${BIN_DIR}/reaper-notes"

# 5. Install Desktop Launcher
echo ">>> Installing desktop entry..."
cat << EOF_DESK > "${DESKTOP_DIR}/com.reaper.Notes.desktop"
[Desktop Entry]
Name=Notes
GenericName=Text Editor & Notes
Comment=Modern GTK4 / Libadwaita text editor with multi-document tabs, syntax highlighting, offline Whisper dictation, and biometric encryption
Exec=${BIN_DIR}/reaper-notes %F
Icon=com.reaper.Notes
Terminal=false
Type=Application
Categories=GNOME;GTK;Utility;TextEditor;Development;
MimeType=text/plain;text/markdown;text/x-c;text/x-c++;text/x-csrc;text/x-chdr;text/x-python;text/x-shellscript;text/x-rust;text/x-go;text/x-javascript;text/x-typescript;application/json;application/xml;text/html;text/css;text/yaml;text/x-makefile;application/x-locked-note;
StartupWMClass=com.reaper.Notes
StartupNotify=true
Keywords=text;editor;notes;pad;markdown;code;whisper;voice;biometrics;locked;encrypted;
Actions=new-note;new-locked-note;

[Desktop Action new-note]
Name=New Note
Exec=${BIN_DIR}/reaper-notes --new
Icon=document-new-symbolic

[Desktop Action new-locked-note]
Name=New Locked Note
Exec=${BIN_DIR}/reaper-notes --new-locked
Icon=channel-secure-symbolic
EOF_DESK
chmod 644 "${DESKTOP_DIR}/com.reaper.Notes.desktop"

# 6. Install Icons
echo ">>> Installing application icons..."
for size in 16x16 24x24 32x32 48x48 64x64 128x128 256x256 512x512; do
    if [ -f "${SCRIPT_DIR}/assets/icons/hicolor/${size}/apps/com.reaper.Notes.png" ]; then
        mkdir -p "${ICON_DIR}/${size}/apps"
        cp "${SCRIPT_DIR}/assets/icons/hicolor/${size}/apps/com.reaper.Notes.png" \
           "${ICON_DIR}/${size}/apps/com.reaper.Notes.png"
        chmod 644 "${ICON_DIR}/${size}/apps/com.reaper.Notes.png"
    fi
done

# 7. Refresh Desktop and Icon Databases
echo ">>> Refreshing desktop application caches..."
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f "${ICON_DIR}" 2>/dev/null || true
fi

# Ensure ~/.local/bin is on user PATH
if [ "$IS_SYSTEM" -eq 0 ]; then
    if [[ ":$PATH:" != *":${HOME}/.local/bin:"* ]]; then
        echo ">>> Note: Ensure ~/.local/bin is in your PATH."
        echo "    Add this to your ~/.bashrc: export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
fi

echo "======================================================================"
echo "           Reaper's Notes installed successfully!                     "
echo "  • Open from GNOME Application Grid as 'Notes'                      "
echo "  • Or run directly from terminal: reaper-notes                      "
echo "======================================================================"
