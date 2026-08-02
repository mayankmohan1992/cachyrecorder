"""Wayland/KDE-native screen capture + active window title via KWin scripting."""
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image

_KWIN_SCRIPT = 'console.info("CACHYREC_TITLE:" + (workspace.activeWindow ? ' \
               '(workspace.activeWindow.resourceClass + "\\u241F" + workspace.activeWindow.caption) : "\\u241F"));'


def grab_screen(dest: Path) -> bool:
    """Silent full-screen capture via Spectacle (no portal prompt on KDE)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            ["spectacle", "-b", "-n", "-f", "-o", str(dest)],
            capture_output=True, timeout=20,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return dest.exists() and dest.stat().st_size > 0 and r.returncode == 0


def active_window() -> tuple[str, str]:
    """Return (app_class, window_title) using a transient KWin script."""
    name = f"cachyrec{int(time.time()*1000)%100000}"
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
            fh.write(_KWIN_SCRIPT)
            js = fh.name
        since = subprocess.run(
            ["date", "+%Y-%m-%d %H:%M:%S"], capture_output=True, text=True
        ).stdout.strip()
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
            ["journalctl", "--user", "--since", since, "-o", "cat", "--no-pager"],
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
        return bin(int(a, 16) ^ int(b, 16)).count("1")
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
    """Idle time via KDE's IdleTime service; 0.0 if unavailable."""
    try:
        out = subprocess.run(
            ["qdbus6", "org.kde.kglobalaccel", "/kglobalaccel"],
            capture_output=True, text=True, timeout=3,
        )
        del out
        r = subprocess.run(
            ["qdbus6", "org.freedesktop.ScreenSaver", "/ScreenSaver", "GetSessionIdleTime"],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip()
        return float(r) if r.replace(".", "").isdigit() else 0.0
    except Exception:
        return 0.0
