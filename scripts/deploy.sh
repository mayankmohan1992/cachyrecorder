#!/usr/bin/env bash
# Deploy the repo working tree to the live runtime path.
#   scripts/deploy.sh            deploy + restart services
#   scripts/deploy.sh --no-restart
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="${CACHYREC_RUNTIME:-$HOME/.local/share/cachyrecorder}"
RESTART=1
[[ "${1:-}" == "--no-restart" ]] && RESTART=0

echo "==> deploying $REPO -> $RUNTIME"

# Byte-compile first: never deploy code that cannot even parse.
python3 -m compileall -q "$REPO/src/cachyrec" >/dev/null

mkdir -p "$RUNTIME"
rsync -a --delete \
      --exclude='__pycache__' \
      "$REPO/src/cachyrec/" "$RUNTIME/cachyrec/"

install -Dm644 "$REPO/systemd/cachyrecorder.service" \
        "$HOME/.config/systemd/user/cachyrecorder.service"
install -Dm644 "$REPO/systemd/cachyrecorder-tray.service" \
        "$HOME/.config/systemd/user/cachyrecorder-tray.service"
install -Dm644 "$REPO/packaging/cachyrecorder.desktop" \
        "$HOME/.local/share/applications/cachyrecorder.desktop"

if [[ -f "$REPO/assets/cachyrecorder.svg" ]]; then
  install -Dm644 "$REPO/assets/cachyrecorder.svg" \
    "$HOME/.local/share/icons/hicolor/scalable/apps/cachyrecorder.svg"
  gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

install -Dm755 "$REPO/scripts/cachyrec-launcher.sh" "$HOME/.local/bin/cachyrec"

systemctl --user daemon-reload

if [[ $RESTART -eq 1 ]]; then
  echo "==> restarting services"
  systemctl --user restart cachyrecorder.service
  systemctl --user restart cachyrecorder-tray.service
fi

echo "==> deployed"
