"""System tray control for CachyRecorder."""
import subprocess
import sys
import time
from datetime import datetime

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (QApplication, QInputDialog, QMenu, QMessageBox,
                             QSystemTrayIcon)

from . import config, store

SERVICE = "cachyrecorder.service"
TRAY_SERVICE = "cachyrecorder-tray.service"


def service_enabled(unit=SERVICE) -> bool:
    """True when the unit is wired to start at login."""
    return systemctl_out("is-enabled", unit).strip() == "enabled"


def set_autostart(on: bool):
    """Enable/disable BOTH units so the tray and recorder agree at login."""
    verb = "enable" if on else "disable"
    for unit in (SERVICE, TRAY_SERVICE):
        systemctl(verb, unit)


def _icon(recording: bool) -> QIcon:
    """Prefer a real theme icon: Plasma's StatusNotifier on Wayland does not
    reliably register a tray item built from a bare in-memory QPixmap."""
    names = (["media-record", "media-playback-start"] if recording
             else ["media-playback-pause", "media-playback-stop"])
    for n in names:
        ic = QIcon.fromTheme(n)
        if not ic.isNull():
            return ic
    # fallback: painted icon
    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#e5484d") if recording else QColor("#8b8d98"))
    p.setPen(QColor("#ffffff"))
    p.drawEllipse(10, 10, 44, 44)
    if not recording:
        p.setBrush(QColor("#ffffff"))
        p.drawRect(24, 22, 6, 20)
        p.drawRect(34, 22, 6, 20)
    p.end()
    return QIcon(pm)


def systemctl(*args):
    return subprocess.run(["systemctl", "--user", *args],
                          capture_output=True, text=True)


def systemctl_out(*args) -> str:
    return systemctl(*args).stdout


def service_active() -> bool:
    return systemctl("is-active", SERVICE).stdout.strip() == "active"


class Tray(QSystemTrayIcon):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.menu = QMenu()
        self.setContextMenu(self.menu)
        self.activated.connect(self.on_click)
        self.rebuild()
        self.timer = QTimer()
        self.timer.timeout.connect(self.rebuild)
        self.timer.start(5000)
        self.show()

    # ---------- state ----------
    def recording(self):
        return service_active() and not config.load().get("paused", False)

    def rebuild(self):
        cfg = config.load()
        active = service_active()
        rec = active and not cfg.get("paused")
        self.setIcon(_icon(rec))

        try:
            conn = store.connect()
            s = store.stats(conn)
            conn.close()
        except Exception:
            s = {"total": 0, "ocr_done": 0, "bytes": 0}

        state = ("Recording" if rec else
                 "Paused" if active else "Stopped (service inactive)")
        mb = s["bytes"] / 1024 / 1024
        self.setToolTip(f"CachyRecorder — {state}\n"
                        f"{s['total']} frames · {s['ocr_done']} indexed · {mb:.0f} MB")

        m = self.menu
        m.clear()
        hdr = QAction(f"● {state}", m)
        hdr.setEnabled(False)
        m.addAction(hdr)
        info = QAction(f"   {s['total']} frames · {mb:.0f} MB", m)
        info.setEnabled(False)
        m.addAction(info)
        m.addSeparator()

        if active:
            act = QAction("▶  Resume recording" if cfg.get("paused")
                          else "⏸  Pause recording", m)
            act.triggered.connect(self.toggle_pause)
            m.addAction(act)
            stop = QAction("⏹  Stop service", m)
            stop.triggered.connect(self.stop_service)
            m.addAction(stop)
        else:
            start = QAction("▶  Start recording service", m)
            start.triggered.connect(self.start_service)
            m.addAction(start)

        m.addSeparator()
        s1 = QAction("🔍  Search recordings…", m)
        s1.triggered.connect(self.open_viewer)
        m.addAction(s1)
        s2 = QAction("🕘  Today's timeline", m)
        s2.triggered.connect(self.open_viewer)
        m.addAction(s2)
        m.addSeparator()

        auto = QAction("Start recording at login", m)
        auto.setCheckable(True)
        auto.setChecked(service_enabled())
        auto.toggled.connect(self.toggle_autostart)
        m.addAction(auto)

        iv = QAction(f"⏱  Capture interval: {cfg['interval_sec']}s", m)
        iv.triggered.connect(self.set_interval)
        m.addAction(iv)
        rt = QAction(f"🗑  Keep history: {cfg['retention_days']} days", m)
        rt.triggered.connect(self.set_retention)
        m.addAction(rt)
        fo = QAction("📂  Open data folder", m)
        fo.triggered.connect(lambda: subprocess.Popen(["xdg-open", str(config.DATA_DIR)]))
        m.addAction(fo)
        lg = QAction("📜  View logs", m)
        lg.triggered.connect(lambda: subprocess.Popen(
            ["konsole", "-e", "journalctl", "--user", "-u", SERVICE, "-f"]))
        m.addAction(lg)
        m.addSeparator()
        q = QAction("✕  Quit tray (recording continues)", m)
        q.triggered.connect(self.app.quit)
        m.addAction(q)

    # ---------- actions ----------
    def on_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.open_viewer()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self.toggle_pause()

    def toggle_pause(self):
        cfg = config.load()
        new = not cfg.get("paused", False)
        config.set_paused(new)
        self.rebuild()
        self.showMessage("CachyRecorder",
                         "Recording paused." if new else "Recording resumed.",
                         _icon(not new), 2500)

    def toggle_autostart(self, on: bool):
        set_autostart(on)
        # read back the real state rather than trusting the click
        actual = service_enabled()
        self.showMessage(
            "CachyRecorder",
            "Will start at login." if actual else "Will NOT start at login.",
            _icon(self.recording()), 3000)
        self.rebuild()

    def start_service(self):
        systemctl("start", SERVICE)
        config.set_paused(False)
        QTimer.singleShot(700, self.rebuild)

    def stop_service(self):
        systemctl("stop", SERVICE)
        QTimer.singleShot(700, self.rebuild)

    def open_viewer(self):
        subprocess.Popen([sys.executable, "-m", "cachyrec.viewer"],
                         cwd=str(config.DATA_DIR.parent / "cachyrecorder"))

    def set_interval(self):
        cfg = config.load()
        v, ok = QInputDialog.getInt(None, "Capture interval",
                                    "Seconds between screenshots:",
                                    cfg["interval_sec"], 1, 600, 1)
        if ok:
            cfg["interval_sec"] = v
            config.save(cfg)
            self.rebuild()

    def set_retention(self):
        cfg = config.load()
        v, ok = QInputDialog.getInt(None, "Retention",
                                    "Delete recordings older than (days, 0=never):",
                                    cfg["retention_days"], 0, 3650, 1)
        if ok:
            cfg["retention_days"] = v
            config.save(cfg)
            self.rebuild()


def main():
    import logging
    import os
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    log = logging.getLogger("tray")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("CachyRecorder")
    app.setDesktopFileName("cachyrecorder")

    # The StatusNotifier host (plasmashell) may not be on the bus yet when a
    # graphical-session service starts. Wait for it before creating the item,
    # otherwise Qt silently falls back to a legacy tray that never appears.
    for i in range(60):
        r = subprocess.run(
            ["busctl", "--user", "--no-pager", "list"],
            capture_output=True, text=True)
        if "org.kde.StatusNotifierWatcher" in r.stdout:
            break
        log.info("waiting for StatusNotifierWatcher (%d)", i)
        time.sleep(1)

    log.info("tray available=%s platform=%s pid=%d",
             QSystemTrayIcon.isSystemTrayAvailable(), app.platformName(), os.getpid())

    tray = Tray(app)

    def verify():
        out = subprocess.run(
            ["busctl", "--user", "get-property", "org.kde.StatusNotifierWatcher",
             "/StatusNotifierWatcher", "org.kde.StatusNotifierWatcher",
             "RegisteredStatusNotifierItems"], capture_output=True, text=True).stdout
        names = subprocess.run(["busctl", "--user", "list", "--no-legend"],
                               capture_output=True, text=True).stdout
        mine = [ln.split()[0] for ln in names.splitlines()
                if len(ln.split()) > 1 and ln.split()[1] == str(os.getpid())]
        ok = any(m in out for m in mine)
        log.info("SNI registered=%s names=%s", ok, mine)
        if not ok:
            log.warning("re-showing tray icon")
            tray.hide()
            tray.show()

    QTimer.singleShot(3000, verify)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
