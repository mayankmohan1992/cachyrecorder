#!/usr/bin/env bash
# CachyRecorder installer — checks dependencies, then deploys.
#
#   ./scripts/install.sh            install and start
#   ./scripts/install.sh --no-start install only
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
START=1
[[ "${1:-}" == "--no-start" ]] && START=0

echo "==> checking dependencies"
miss=()
need_cmd() { command -v "$1" >/dev/null || miss+=("$2"); }

need_cmd python3   python
need_cmd spectacle spectacle
need_cmd tesseract tesseract
need_cmd qdbus6    qt6-tools

if ! /usr/bin/python3 -c "import PyQt6.QtWidgets" 2>/dev/null; then
  miss+=("python-pyqt6")
fi
if ! /usr/bin/python3 -c "import PIL" 2>/dev/null; then
  miss+=("python-pillow")
fi
# OCR shells out to the tesseract binary; no python binding required.
if ! tesseract --list-langs 2>/dev/null | grep -q .; then
  miss+=("tesseract-data-eng")
fi

if (( ${#miss[@]} )); then
  echo "!! missing: ${miss[*]}"
  echo
  echo "   Arch / CachyOS:"
  echo "     sudo pacman -S --needed ${miss[*]} tesseract-data-eng"
  echo
  echo "   Note: CachyRecorder runs on the SYSTEM python (/usr/bin/python3)"
  echo "   because it needs the distro PyQt6. Do not install it in a venv."
  exit 1
fi
echo "    all dependencies present"

if [[ "${XDG_SESSION_TYPE:-}" != "wayland" ]]; then
  echo "!! warning: session is '${XDG_SESSION_TYPE:-unknown}', tested on wayland"
fi
if [[ "${XDG_CURRENT_DESKTOP:-}" != *KDE* ]]; then
  echo "!! warning: desktop is '${XDG_CURRENT_DESKTOP:-unknown}'."
  echo "   Capture uses Spectacle and window titles use KWin scripting;"
  echo "   both are KDE-specific. See README 'Porting' before filing a bug."
fi

"$REPO/scripts/deploy.sh" $([[ $START -eq 0 ]] && echo --no-restart)

if (( START )); then
  echo
  echo "==> enabling at login"
  systemctl --user enable --now cachyrecorder.service cachyrecorder-tray.service
  echo
  echo "Installed. Look for the tray icon in your panel."
  echo "  cachyrec status          # what it is doing"
  echo "  cachyrec search <query>  # search your history"
  echo "  cachyrec gui             # open the search window"
fi
