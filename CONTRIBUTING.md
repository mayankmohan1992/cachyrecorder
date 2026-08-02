# Contributing to CachyRecorder

## Ground rules

- `main` is always deployable. Never commit to it directly.
- Every change lands on a branch, is deployed to a live system, and must pass
  `scripts/verify.sh` before merge.
- Data never enters git. `frames/`, `index.db`, and `config.json` are ignored.

## Repo layout

```
src/cachyrec/     application code (deployed to ~/.local/share/cachyrecorder)
systemd/          user units
packaging/        .desktop entry
scripts/          deploy.sh, verify.sh, launcher
assets/           icons
docs/             design notes
```

The repo is **not** the runtime. `scripts/deploy.sh` copies the working tree to
`~/.local/share/cachyrecorder`, so a broken branch can never break live recording
until you deploy it.

## Workflow

```bash
git switch -c feat/my-thing
# edit src/cachyrec/...
scripts/deploy.sh          # push to runtime + restart services
scripts/verify.sh          # must print "0 failed"
git commit -am "feat: my thing"
git switch main && git merge --no-ff feat/my-thing
```

If `verify.sh` fails, fix it or roll back:

```bash
git switch main && scripts/deploy.sh   # restore last good state
```

## Branch naming

| prefix | use |
|---|---|
| `feat/` | new capability |
| `fix/` | bug fix |
| `perf/` | speed / disk / CPU |
| `docs/` | documentation only |
| `chore/` | tooling, packaging |

## Commit style

Conventional commits: `feat:`, `fix:`, `perf:`, `docs:`, `chore:`, `refactor:`.

## What verify.sh checks

1. Sources byte-compile
2. All modules import under system python
3. Both systemd units are active
4. Neither unit is restart-looping
5. Frame count actually advances (real capture)
6. OCR backlog is not runaway
7. FTS search executes
8. Tray is registered with Plasma's StatusNotifierWatcher
9. `cachyrec` CLI responds

Checks 5 and 8 are the ones that catch real regressions — 8 exists because a
tray icon can silently fail to register on Wayland with no error at all.

## Environment assumptions

- KDE Plasma 6 on Wayland (uses Spectacle + KWin scripting)
- System python with distro `PyQt6` and `Pillow` — **not** a venv
- `tesseract` for OCR

Patches that add support for other desktops are welcome, but must keep the KDE
path working and gate new backends behind config.
