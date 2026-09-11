#!/usr/bin/env bash
# ==============================================================================
# Reaper's Notes: Clean Uninstaller
# ==============================================================================

set -e

echo "======================================================================"
echo "          Uninstalling Reaper's Notes                                 "
echo "======================================================================"

# Determine scopes
if [ "$(id -u)" -eq 0 ]; then
    rm -rf /usr/share/reapers-notes
    rm -f /usr/bin/reaper-notes
    rm -f /usr/share/applications/com.reaper.Notes.desktop
    find /usr/share/icons/hicolor -name "com.reaper.Notes.png" -delete 2>/dev/null || true
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database /usr/share/applications 2>/dev/null || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null || true
    fi
    echo ">>> System-wide installation removed."
fi

# Also clean local user directories if present
rm -rf "${HOME}/.local/share/reapers-notes"
rm -f "${HOME}/.local/bin/reaper-notes"
rm -f "${HOME}/.local/share/applications/com.reaper.Notes.desktop"
find "${HOME}/.local/share/icons/hicolor" -name "com.reaper.Notes.png" -delete 2>/dev/null || true

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "${HOME}/.local/share/applications" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f "${HOME}/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo ">>> Local user files removed."
echo "======================================================================"
echo " Reaper's Notes uninstalled cleanly. (Your saved notes remain intact)."
echo "======================================================================"
