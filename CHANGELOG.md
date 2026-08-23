# Changelog

## 0.2.0 — 2026-08-23

### Security

- **Screen captures no longer touch `/tmp`.** Temporary frames now go to
  `$XDG_RUNTIME_DIR/cachyrec/` (mode 0700, tmpfs). Previously they were
  world-readable files with predictable names in a world-writable directory —
  readable by any local user and open to symlink attacks.
- **Frames and the OCR index are now private.** Both systemd units set
  `UMask=0077`, and `deploy.sh` hardens the existing data tree once. Frames
  and `index.db` were `644` (readable by every local user) — they contain
  everything ever shown on screen, including anything typed into terminals.
- The KWin scripting tempfile moved to the same private directory.

### Fixed

- **Tray "Start recording at login" could silently disable itself.** The tray
  menu rebuilds periodically; if the `systemctl is-enabled` probe hiccuped
  during a rebuild, `setChecked(False)` fired the toggled handler and actually
  disabled both units — recording then died at next login. The initial check
  state no longer emits signals.
- **The merge gate now catches the two failure modes that bit real users.**
  - Services silently becoming *disabled* killed recording until manually
    restarted; `verify.sh` now asserts both units are enabled, not just active.
  - A stale deployment once shipped a crashing viewer while checks stayed
    green against the repo copy; `verify.sh` now fails if the deployed
    runtime differs from the working tree ("runtime DRIFTED from repo").
- **Purge no longer leaks disk on failure.** If an expired frame's file cannot
  be deleted, the orphan is logged by the daemon and printed by the CLI
  instead of being swallowed, leaving unindexed webp files forever.
- **OCR failures are counted and visible.** A nonzero tesseract exit is now
  treated as a failure; `cachyrec status` shows the running count instead of
  failing frames silently indexing as empty text.

### Changed

- Merge gate expanded from 13 to 16 checks.

## 0.1.1 — 2026-08-20

- Capture uses `spectacle --new-instance`, so the recorder never registers on
  Spectacle's single-instance D-Bus name. Launching Spectacle from the
  Application Launcher while recording now closes the launcher normally
  instead of treating it as "already running".
- The daemon yields capture ticks while the user's own Spectacle session is
  open (`spectacle_running()` check).
- `pause_on_idle_sec` actually works: idle detection falls back to
  screen-change deduplication, since KDE Wayland exposes no idle API.
- Tray icon uses theme/file icons so it registers reliably on Wayland.

## 0.1.0 — 2026-08-02

Initial release: periodic full-screen capture via Spectacle, dhash duplicate
suppression, OCR (tesseract) into SQLite FTS5, tray control with pause/resume
and autostart toggle, search viewer GUI, retention purge.
