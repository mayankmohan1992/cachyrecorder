#!/usr/bin/env bash
# CachyRecorder launcher — system python, isolated from any active venv.
export PYTHONPATH="$HOME/.local/share/cachyrecorder"
unset VIRTUAL_ENV
cd "$HOME/.local/share/cachyrecorder" || exit 1
exec /usr/bin/python3 -m cachyrec.cli "$@"
