#!/usr/bin/env bash
# CachyRecorder uninstaller.
#
#   ./scripts/uninstall.sh          remove the app, keep recordings
#   ./scripts/uninstall.sh --purge  remove the app AND all recordings
set -uo pipefail

DATA="${CACHYREC_HOME:-$HOME/.local/share/cachyrecorder}"
PURGE=0
[[ "${1:-}" == "--purge" ]] && PURGE=1

echo "==> stopping services"
systemctl --user disable --now cachyrecorder.service cachyrecorder-tray.service 2>/dev/null
rm -f "$HOME/.config/systemd/user/cachyrecorder.service" \
      "$HOME/.config/systemd/user/cachyrecorder-tray.service"
systemctl --user daemon-reload

echo "==> removing launcher, desktop entry, icons"
rm -f "$HOME/.local/bin/cachyrec"
rm -f "$HOME/.local/share/applications/cachyrecorder.desktop"
rm -f "$HOME"/.local/share/icons/hicolor/scalable/apps/cachyrecorder*.svg
rm -f "$HOME/.config/autostart/cachyrecorder-tray.desktop"
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "==> removing program files"
rm -rf "$DATA/cachyrec"

if (( PURGE )); then
  echo "==> deleting recordings and index"
  rm -rf "$DATA"
  echo "    removed $DATA"
else
  echo
  echo "Recordings kept at: $DATA"
  echo "  delete them with: rm -rf '$DATA'"
fi

echo "Uninstalled."
