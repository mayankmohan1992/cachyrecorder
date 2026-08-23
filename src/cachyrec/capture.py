"""Wayland/KDE-native screen capture + active window title via KWin scripting."""
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from PIL import Image

_KWIN_SCRIPT = (
    'console.info("CACHYREC_TITLE:" + (workspace.activeWindow ? '
    '(workspace.activeWindow.resourceClass + "\\u241F" + '
    'workspace.activeWindow.caption) : "\\u241F"));'
)


def spectacle_running() -> bool:
    """True when Spectacle already holds its D-Bus name (user has it open).

    Spectacle is single-instance on org.kde.Spectacle. The recorder must not
    fire `spectacle -b` while the user is using the GUI, or it steals the bus
    name and the user's capture breaks.
    """
    try:
        out = subprocess.run(["busctl", "--user", "list"],
                             capture_output=True, text=True, timeout=3).stdout
        for line in out.splitlines():
            if line.startswith("org.kde.Spectacle"):
                # column 2 is the owner; "-" means activatable but not running
                return line.split()[1] != "-"
    except Exception:
        pass
    return False


def grab_screen(dest: Path) -> bool:
    """Silent full-screen capture via Spectacle (no portal prompt on KDE)."""
    if spectacle_running():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            # -i: don't register on org.kde.Spectacle (single-instance bus name),
            # so launching Spectacle from the menu while we record doesn't make
            # KDE think Spectacle is "already running" (which stops the menu
            # from closing). See fix/spectacle-busy.
            ["spectacle", "-b", "-n", "-i", "-f", "-o", str(dest)],
            capture_output=True, timeout=20,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return dest.exists() and dest.stat().st_size > 0 and r.returncode == 0


def _tmpdir() -> Path:
    """Private 0700 scratch dir (tmpfs); never /tmp for screen-derived data."""
    d = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "cachyrec"
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    return d


def active_window() -> tuple[str, str]:
    """Return (app_class, window_title) using a transient KWin script."""
    name = f"cachyrec{int(time.time()*1000)%100000}"
    try:
        js = _tmpdir() / f"{name}.js"
        js.write_text(_KWIN_SCRIPT)
        js = str(js)
        sid = subprocess.run(
            ["qdbus6", "org.kde.KWin", "/Scripting",
             "org.kde.kwin.Scripting.loadScript", js, name],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if not sid.isdigit():
            return "", ""
        subprocess.run(["qdbus6", "org.kde.KWin", f"/Scripting/Script{sid}",
                        "org.kde.kwin.Script.run"], capture_output=True, timeout=5)
        time.sleep(0.15)
        out = subprocess.run(
            ["journalctl", "--user", "--since",
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "-o", "cat",
             "--no-pager"],
            capture_output=True, text=True, timeout=8,
        ).stdout
        subprocess.run(["qdbus6", "org.kde.KWin", "/Scripting",
                        "org.kde.kwin.Scripting.unloadScript", name],
                       capture_output=True, timeout=5)
        Path(js).unlink(missing_ok=True)
        hits = [ln for ln in out.splitlines() if "CACHYREC_TITLE:" in ln]
        if hits:
            payload = hits[-1].split("CACHYREC_TITLE:", 1)[1]
            app, _, title = payload.partition("\u241f")
            return app.strip(), title.strip()
    except Exception:
        pass
    return "", ""


def dhash(img: Image.Image, size: int = 8) -> str:
    """Difference hash for duplicate-frame detection."""
    g = img.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
    px = list(g.getdata())
    bits = []
    for row in range(size):
        for col in range(size):
            i = row * (size + 1) + col
            bits.append("1" if px[i] > px[i + 1] else "0")
    return f"{int(''.join(bits), 2):016x}"


def hamming(a: str, b: str) -> int:
    if not a or not b:
        return 999
    try:
        return (int(a, 16) ^ int(b, 16)).bit_count()
    except ValueError:
        return 999


def is_locked() -> bool:
    try:
        out = subprocess.run(
            ["qdbus6", "org.freedesktop.ScreenSaver", "/ScreenSaver", "GetActive"],
            capture_output=True, text=True, timeout=4,
        ).stdout.strip().lower()
        return out == "true"
    except Exception:
        return False


def idle_seconds() -> float:
    """Idle seconds, or -1.0 when the session reports none.

    Callers treat -1.0 as "unknown" and fall back to screen-change detection.
    """
    try:
        r = subprocess.run(
            ["qdbus6", "org.freedesktop.ScreenSaver", "/ScreenSaver",
             "GetSessionIdleTime"], capture_output=True, text=True, timeout=3)
        v = r.stdout.strip()
        if r.returncode == 0 and v.isdigit():
            return float(v)
    except Exception:
        pass
    return -1.0
