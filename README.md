# CachyRecorder

Search everything you've seen on your screen.

CachyRecorder periodically captures your screen, runs OCR over each frame, and
indexes the text so you can find that thing you saw three days ago and can't
name. It's a Linux-native answer to Microsoft Recall / Rewind — built for
**KDE Plasma 6 on Wayland**, and inspired by
[Windrecorder](https://github.com/yuka-friends/Windrecorder) (Windows-only).

Everything stays on your machine. No cloud, no telemetry, no network calls.

```
cachyrec search "invoice acme"
2026-08-02 14:53   [firefox]  Acme Corp — Invoice #4471
2026-07-29 09:12   [okular]   invoice_acme_july.pdf
```

---

## Why not just run Windrecorder?

You can't — it's structurally Windows-bound: `pywin32` window hooks,
Windows.Media.Ocr, `ffmpeg -f gdigrab`, `.bat` installers. CachyRecorder keeps
the *architecture* (capture → dedup → OCR → FTS index → search UI) and
reimplements every layer on Linux equivalents.

**On continuous video:** upstream records video with ffmpeg. That isn't possible
here — FFmpeg has no PipeWire input device on any distro
([open upstream request](https://trac.ffmpeg.org/ticket/10742)), and `kmsgrab`
needs `CAP_SYS_ADMIN`. So CachyRecorder uses Windrecorder's own *screenshot
record mode*, driven by Spectacle. Measured over ~1 hour of normal desktop use:

| | screenshot mode | continuous 1080p video |
|---|---|---|
| storage | **10 MB/hour** | ~400–700 MB/hour |
| CPU | **0.9% of one core** | continuous encode |
| dedup | **72% of ticks dropped** | encodes regardless |
| permission | none needed | portal grant |

For a *search* tool this is the better trade: the dropped frames were identical
and had nothing new to index.

---

## Requirements

- KDE Plasma 6 on Wayland (see [Porting](#porting) for other setups)
- `python` (3.11+), `python-pyqt6`, `python-pillow`
- `spectacle`, `tesseract`, `tesseract-data-eng`, `qt6-tools`

```bash
sudo pacman -S --needed python python-pyqt6 python-pillow \
                        spectacle tesseract tesseract-data-eng qt6-tools
```

> CachyRecorder runs on the **system python** (`/usr/bin/python3`) because it
> needs the distro PyQt6 build. Don't install it into a venv.

## Install

```bash
git clone https://github.com/mayankmohan1992/cachyrecorder.git
cd cachyrecorder
./scripts/install.sh
```

The installer verifies dependencies, deploys to
`~/.local/share/cachyrecorder`, and enables two systemd user services. A tray
icon appears in your panel.

To remove:

```bash
./scripts/uninstall.sh          # keeps your recordings
./scripts/uninstall.sh --purge  # deletes them too
```

---

## Usage

### Tray

| action | result |
|---|---|
| left-click | open the search window |
| middle-click | pause / resume recording |
| right-click | full menu |

The right-click menu has pause, capture interval, retention, **Start recording
at login**, open data folder, and logs. The icon shows a red dot while
recording and grey pause bars when stopped.

### Command line

```bash
cachyrec status                  # frames, index size, disk usage
cachyrec search <query>          # search OCR text
cachyrec search "term" --limit 5
cachyrec gui                     # search window
cachyrec pause / resume
cachyrec set interval_sec 10     # any config key
cachyrec purge --days 7          # delete frames older than N days
```

### Search syntax

Backed by SQLite FTS5:

| query | matches |
|---|---|
| `invoice acme` | both words (AND is implicit) |
| `"exact phrase"` | that exact phrase |
| `invoice OR receipt` | either |
| `invoice NOT draft` | excludes |
| `inv*` | prefix |

---

## Configuration

`~/.local/share/cachyrecorder/config.json` — edit directly or use `cachyrec set`.
Changes apply within one capture cycle; no restart needed.

| key | default | meaning |
|---|---|---|
| `interval_sec` | 5 | seconds between captures |
| `similarity_skip` | 4 | dhash distance below which a frame is a duplicate and dropped |
| `max_width` | 1600 | downscale stored frames to this width |
| `ocr_lang` | eng | tesseract language (`pacman -S tesseract-data-hin` for more) |
| `retention_days` | 30 | auto-delete older frames (0 = keep forever) |
| `pause_on_idle_sec` | 180 | back off to a slow poll once the screen is unchanged this long (0 = off) |
| `exclude_title_keywords` | password managers | skip capture when the window title or app matches |
| `paused` | false | toggled by the tray |

### Privacy

Capture is skipped when the screen is locked, and for any window whose title or
app matches `exclude_title_keywords` — by default Bitwarden, KeePass,
1Password, and private browsing windows. Add your own:

```bash
cachyrec set exclude_title_keywords '["Bitwarden","Signal","banking"]'
```

Frames live in `~/.local/share/cachyrecorder/frames/` as WebP, and the index in
`index.db`. Both are plain files you can delete at any time. Nothing is
encrypted — anyone with read access to your home directory can read them.

---

## How it works

```
 ┌──────────┐   ┌────────┐   ┌──────────┐   ┌───────────┐
 │ Spectacle│──▶│ dhash  │──▶│ tesseract│──▶│ SQLite    │
 │ capture  │   │ dedup  │   │ OCR      │   │ FTS5 index│
 └──────────┘   └────────┘   └──────────┘   └───────────┘
       │             │                            │
   every 5s    drop if screen              cachyrec search
               unchanged (72%)             / GUI / tray
```

Two systemd user services: `cachyrecorder.service` (capture + OCR worker) and
`cachyrecorder-tray.service` (tray). Window titles come from a KWin script over
D-Bus, since Wayland gives no global window access.

---

## Troubleshooting

**Tray icon missing.**
```bash
systemctl --user status cachyrecorder-tray.service
journalctl --user -u cachyrecorder-tray.service -n 30
```
Look for `SNI registered=True`. If the service is running but the icon is
absent, your panel may lack a System Tray widget.

**No new frames.** Often correct behaviour — a static screen is deduplicated
away. Confirm with `cachyrec status`, and check `paused`.

**OCR text is garbled.** Expected on dense UI text at small sizes. It's tuned
for keyword recall, not verbatim extraction. Raising `max_width` helps at the
cost of disk.

**Disk filling up.** Lower `retention_days`, raise `interval_sec`, or
`cachyrec purge --days 7`.

**`ModuleNotFoundError: PyQt6`.** Something is running the code under a venv
python. The launcher clears `VIRTUAL_ENV`/`PYTHONPATH`; check you're invoking
`cachyrec`, not `python -m cachyrec.*` from an active venv.

---

## Porting

Two components are KDE-specific and are the only things needing replacement:

| component | file | KDE implementation | swap for |
|---|---|---|---|
| screen capture | `capture.py: grab_screen()` | `spectacle -b -n -f` | `grim` (wlroots), `gnome-screenshot` |
| window title | `capture.py: active_window()` | KWin script over D-Bus | `swaymsg -t get_tree`, `xdotool` (X11) |

The rest — dedup, OCR, index, GUI, tray — is desktop-agnostic. PRs welcome.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Short version: branch, deploy, and
`make check` must print `0 failed` before anything merges.

## License

GPL-2.0, matching upstream Windrecorder.

## Credits

Architecture and inspiration: [Windrecorder](https://github.com/yuka-friends/Windrecorder)
by [yuka-friends](https://github.com/yuka-friends).
