# CachyRecorder

A Linux-native reimplementation of [Windrecorder](https://github.com/yuka-friends/Windrecorder)
for **CachyOS + KDE Plasma 6 on Wayland**.

Records your screen periodically, OCRs every frame, and lets you full-text search
everything you have ever seen — with a tray icon to pause/resume.

## Why this is a rewrite, not a port

Upstream Windrecorder is Windows-only at its core:

| Windrecorder (Windows)          | CachyRecorder (this)                       |
|---------------------------------|--------------------------------------------|
| `ffmpeg -f gdigrab` capture     | `spectacle -b -n -f` (KDE, silent, Wayland) |
| `pywin32` active-window hooks   | KWin scripting over D-Bus                   |
| Windows.Media.Ocr / PaddleOCR   | `tesseract`                                 |
| `.bat` installers, Poetry venv  | systemd user services, system Python        |
| Streamlit web UI                | native PyQt6 app + tray                     |
| video segments + keyframes      | dedup'd WebP frames (dhash)                 |

Ffmpeg on this system has **no PipeWire input**, so continuous video capture under
Wayland is not possible; upstream's *screenshot record mode* is the model used here.

## Layout

```
~/.local/share/cachyrecorder/
├── cachyrec/
│   ├── config.py    settings (JSON, hot-reloaded each capture tick)
│   ├── store.py     SQLite + FTS5 index
│   ├── capture.py   Spectacle capture, KWin titles, dhash, idle/lock
│   ├── daemon.py    capture loop + OCR worker + retention worker
│   ├── viewer.py    PyQt6 search & timeline GUI
│   ├── tray.py      system tray control
│   └── cli.py       `cachyrec` command
├── frames/YYYY-MM-DD/HHMMSS_<ts>.webp
├── index.db
└── config.json
```

## Services

```bash
systemctl --user status cachyrecorder          # recorder daemon
systemctl --user status cachyrecorder-tray     # tray icon
```
Both are `enabled` and start with your graphical session.

## Tray

Red dot = recording, pause glyph = paused.

- **Left-click** → open search window
- **Middle-click** → toggle pause
- **Right-click** → menu: pause/resume, stop service, search, timeline,
  interval, retention, open data folder, view logs

## CLI

```bash
cachyrec status                 # frames, disk usage, settings
cachyrec search invoice acme    # full-text search with snippets
cachyrec pause / resume
cachyrec gui                    # search window
cachyrec set interval_sec 10
cachyrec set retention_days 60
cachyrec set exclude_title_keywords "Bitwarden,KeePass,Private Browsing"
```

## Settings (`config.json`)

| key | default | meaning |
|---|---|---|
| `interval_sec` | 5 | seconds between captures |
| `similarity_skip` | 4 | dhash distance below which a frame is a duplicate and dropped |
| `webp_quality` | 55 | stored frame quality |
| `max_width` | 1600 | downscale width |
| `ocr_lang` | eng | tesseract language (`pacman -S tesseract-data-hin` for more) |
| `retention_days` | 30 | auto-delete older frames (0 = keep forever) |
| `pause_on_idle_sec` | 180 | back off to a slow poll once the screen has been unchanged this long (0 = off). KDE Wayland exposes no idle API, so this uses screen-change detection rather than input timing |
| `exclude_title_keywords` | password managers | skip capture when window title/app matches |
| `paused` | false | toggled by the tray |

## Privacy

- 100% local: no network calls, no telemetry.
- Capture is skipped while the screen is locked, while idle, and for any window
  whose title/app matches `exclude_title_keywords`.
- Delete everything: `systemctl --user stop cachyrecorder && rm -rf ~/.local/share/cachyrecorder/{frames,index.db}`

## Resource use

~50 kB per stored frame; identical frames are dropped, so an idle screen costs
almost nothing. At 5s intervals expect roughly 200–600 MB/day of active use.
The daemon runs at `Nice=10` with idle I/O priority.

## Notes / gotchas

- The daemon must run under **system Python** (`/usr/bin/python3`), not a venv —
  it needs the distro `PyQt6` and `Pillow`. The units set `PYTHONPATH` explicitly.
- The tray icon must use a **theme icon** (`QIcon.fromTheme`). Plasma's
  StatusNotifier on Wayland will not register an item built from a bare
  in-memory `QPixmap`.
- `tray.py` waits for `org.kde.StatusNotifierWatcher` before creating the item,
  since a `graphical-session.target` service can start before plasmashell.
