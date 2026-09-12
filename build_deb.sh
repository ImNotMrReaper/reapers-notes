#!/usr/bin/env bash
# ==============================================================================
# Builds reapers-notes_1.0.0_amd64.deb for Ubuntu / Debian Linux
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build/deb"
VERSION="1.2.1"
PKG_NAME="reapers-notes"
ARCH="$(dpkg --print-architecture 2>/dev/null || echo "amd64")"
DEB_FILE="${PKG_NAME}_${VERSION}_${ARCH}.deb"

echo "======================================================================"
echo " Packaging ${PKG_NAME} v${VERSION} (${ARCH})"
echo "======================================================================"

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}/DEBIAN"
mkdir -p "${BUILD_DIR}/usr/bin"
mkdir -p "${BUILD_DIR}/usr/share/${PKG_NAME}/styles"
mkdir -p "${BUILD_DIR}/usr/share/${PKG_NAME}/plugins"
mkdir -p "${BUILD_DIR}/usr/share/applications"

# 1. Copy source code files
cp "${SCRIPT_DIR}/src/reaper_notes/"*.py "${BUILD_DIR}/usr/share/${PKG_NAME}/"
cp "${SCRIPT_DIR}/src/reaper_notes/"*.css "${BUILD_DIR}/usr/share/${PKG_NAME}/"
if [ -f "${SCRIPT_DIR}/src/reaper_notes/libwhisper_easy.so" ]; then
    cp "${SCRIPT_DIR}/src/reaper_notes/libwhisper_easy.so" "${BUILD_DIR}/usr/share/${PKG_NAME}/"
fi
if [ -d "${SCRIPT_DIR}/src/reaper_notes/styles" ]; then
    cp "${SCRIPT_DIR}/src/reaper_notes/styles/"*.xml "${BUILD_DIR}/usr/share/${PKG_NAME}/styles/" 2>/dev/null || true
fi
if [ -d "${SCRIPT_DIR}/src/reaper_notes/plugins" ]; then
    cp "${SCRIPT_DIR}/src/reaper_notes/plugins/"*.py "${BUILD_DIR}/usr/share/${PKG_NAME}/plugins/" 2>/dev/null || true
    chmod 755 "${BUILD_DIR}/usr/share/${PKG_NAME}/plugins"/*.py 2>/dev/null || true
fi
chmod 755 "${BUILD_DIR}/usr/share/${PKG_NAME}"/*.py
chmod 644 "${BUILD_DIR}/usr/share/${PKG_NAME}"/*.css 2>/dev/null || true

# 2. Copy wrapper executable
cp "${SCRIPT_DIR}/bin/reaper-notes" "${BUILD_DIR}/usr/bin/reaper-notes"
chmod 755 "${BUILD_DIR}/usr/bin/reaper-notes"

# 3. Copy desktop entry
cp "${SCRIPT_DIR}/assets/com.reaper.Notes.desktop" "${BUILD_DIR}/usr/share/applications/"
chmod 644 "${BUILD_DIR}/usr/share/applications/com.reaper.Notes.desktop"

# 4. Copy icons
for size in 16x16 32x32 48x48 64x64 128x128 256x256; do
    if [ -f "${SCRIPT_DIR}/assets/icons/hicolor/${size}/apps/com.reaper.Notes.png" ]; then
        mkdir -p "${BUILD_DIR}/usr/share/icons/hicolor/${size}/apps"
        cp "${SCRIPT_DIR}/assets/icons/hicolor/${size}/apps/com.reaper.Notes.png" \
           "${BUILD_DIR}/usr/share/icons/hicolor/${size}/apps/com.reaper.Notes.png"
        chmod 644 "${BUILD_DIR}/usr/share/icons/hicolor/${size}/apps/com.reaper.Notes.png"
    fi
done

# 5. Create Debian Control File
cat << 'EOF_CONTROL' > "${BUILD_DIR}/DEBIAN/control"
Package: reapers-notes
Version: 1.2.0
Section: editors
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.10), python3-gi, python3-gi-cairo, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-gtksource-5, python3-cryptography, libpipewire-0.3-0
Recommends: zenity, pipewire, pipewire-audio-client-libraries
Maintainer: Mr-Reaper <admin@localhost>
Homepage: https://github.com/ImNotMrReaper/reapers-notes
Description: Modern GTK4 / Libadwaita text editor and biometric encrypted notes application
 High-performance desktop text editor and encrypted note vault:
  - Multi-document tabbed interface with unsaved changes safety
  - In-editor interactive Find and Replace (Ctrl+F, Ctrl+H)
  - 176+ language syntax highlighters & instant Plain Text toggle
  - Military-grade AES-256-GCM note encryption with GNOME Tri-Factor Biometrics
  - Real-time streaming voice dictation with sub-70ms local CPU Whisper
  - Adaptive system theme (Light/Dark/Accent) and pure OLED Pitch Black mode
EOF_CONTROL

# 6. Post-Installation Script
cat << 'EOF_POSTINST' > "${BUILD_DIR}/DEBIAN/postinst"
#!/bin/sh
set -e

if [ -x /usr/bin/update-desktop-database ]; then
    update-desktop-database -q /usr/share/applications || true
fi

if [ -x /usr/bin/gtk-update-icon-cache ]; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi

echo "======================================================================"
echo " Reaper's Notes installed successfully!"
echo " Launch from application menu as 'Notes' or via terminal: reaper-notes"
echo "======================================================================"
exit 0
EOF_POSTINST
chmod 755 "${BUILD_DIR}/DEBIAN/postinst"

# 7. Post-Removal Script
cat << 'EOF_POSTRM' > "${BUILD_DIR}/DEBIAN/postrm"
#!/bin/sh
set -e

if [ -x /usr/bin/update-desktop-database ]; then
    update-desktop-database -q /usr/share/applications || true
fi

if [ -x /usr/bin/gtk-update-icon-cache ]; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
exit 0
EOF_POSTRM
chmod 755 "${BUILD_DIR}/DEBIAN/postrm"

# 8. Build Debian Package
dpkg-deb --build --root-owner-group "${BUILD_DIR}" "${SCRIPT_DIR}/${DEB_FILE}"

echo "======================================================================"
echo " Created: ${SCRIPT_DIR}/${DEB_FILE}"
echo " Size: $(ls -lh "${SCRIPT_DIR}/${DEB_FILE}" | awk '{print $5}')"
echo " Verify with: dpkg-deb -I ${SCRIPT_DIR}/${DEB_FILE}"
echo " Install with: sudo dpkg -i ${SCRIPT_DIR}/${DEB_FILE}"
echo "======================================================================"
