"""Search & timeline viewer (PyQt6)."""
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from . import config, store


def human_size(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}PB"


class Viewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.conn = store.connect()
        self.rows = []
        self.setWindowTitle("CachyRecorder — Search your screen history")
        self.resize(1400, 860)

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)

        # ---- search bar ----
        bar = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(
            "Search everything you've seen…  (text on screen, window titles, app names)")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.returnPressed.connect(self.do_search)
        self.search_box.setMinimumHeight(34)
        bar.addWidget(self.search_box, 1)

        self.scope = QComboBox()
        self.scope.addItems(["All time", "Today", "Last 7 days", "Last 30 days"])
        bar.addWidget(self.scope)

        btn = QPushButton("Search")
        btn.clicked.connect(self.do_search)
        bar.addWidget(btn)
        tbtn = QPushButton("Today's timeline")
        tbtn.clicked.connect(self.show_today)
        bar.addWidget(tbtn)
        outer.addLayout(bar)

        # ---- split: results | preview ----
        split = QSplitter(Qt.Orientation.Horizontal)
        self.results = QListWidget()
        self.results.currentRowChanged.connect(self.show_frame)
        self.results.setMinimumWidth(430)
        split.addWidget(self.results)

        right = QWidget()
        rl = QVBoxLayout(right)
        self.meta = QLabel("Search above, or open today's timeline.")
        self.meta.setWordWrap(True)
        self.meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rl.addWidget(self.meta)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.image = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(self.image)
        rl.addWidget(self.scroll, 1)

        nav = QHBoxLayout()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(self.results.setCurrentRow)
        prev = QPushButton("◀ Prev")
        prev.clicked.connect(lambda: self.step(-1))
        nxt = QPushButton("Next ▶")
        nxt.clicked.connect(lambda: self.step(1))
        opend = QPushButton("Open folder")
        opend.clicked.connect(self.open_folder)
        nav.addWidget(prev)
        nav.addWidget(self.slider, 1)
        nav.addWidget(nxt)
        nav.addWidget(opend)
        rl.addLayout(nav)

        split.addWidget(right)
        split.setSizes([440, 960])
        outer.addWidget(split, 1)

        self.setStatusBar(QStatusBar())
        self.refresh_stats()
        QTimer.singleShot(80, self.search_box.setFocus)

    # ---------- data ----------
    def refresh_stats(self):
        s = store.stats(self.conn)
        first = (datetime.fromtimestamp(s["first_ts"]).strftime("%Y-%m-%d")
                 if s["first_ts"] else "—")
        self.statusBar().showMessage(
            f"{s['total']} frames · {s['ocr_done']} indexed · "
            f"{human_size(s['bytes'])} on disk · since {first}")

    def scope_bounds(self):
        now = datetime.now()
        idx = self.scope.currentIndex()
        if idx == 1:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif idx == 2:
            start = now - timedelta(days=7)
        elif idx == 3:
            start = now - timedelta(days=30)
        else:
            return None
        return int(start.timestamp()), int(now.timestamp())

    def do_search(self):
        q = self.search_box.text().strip()
        if not q:
            return self.show_today()
        rows = store.search(self.conn, q, limit=500)
        b = self.scope_bounds()
        if b:
            rows = [r for r in rows if b[0] <= r["ts"] <= b[1]]
        self.populate(rows, f"{len(rows)} results for “{q}”")

    def show_today(self):
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        rows = store.range_frames(self.conn, int(start.timestamp()),
                                  int(datetime.now().timestamp()))
        self.populate(list(rows), f"Today — {len(rows)} frames")

    def populate(self, rows, note):
        self.rows = rows
        self.results.clear()
        for r in rows:
            t = datetime.fromtimestamp(r["ts"]).strftime("%b %d  %H:%M:%S")
            title = (r["title"] or "")[:60]
            item = QListWidgetItem(f"{t}   [{r['app'] or '?'}]\n{title}")
            # sqlite3.Row has no __contains__, so .keys() is required here
            snip = r["snip"] if "snip" in r.keys() else None  # noqa: SIM118
            if snip:
                item.setToolTip(snip)
            self.results.addItem(item)
        self.slider.setMaximum(max(0, len(rows) - 1))
        self.meta.setText(note)
        self.refresh_stats()
        if rows:
            self.results.setCurrentRow(0)
        else:
            self.image.clear()

    def step(self, d):
        r = self.results.currentRow() + d
        if 0 <= r < len(self.rows):
            self.results.setCurrentRow(r)

    def show_frame(self, idx):
        if not (0 <= idx < len(self.rows)):
            return
        r = self.rows[idx]
        p = Path(r["path"])
        if p.exists():
            pm = QPixmap(str(p))
            w = max(400, self.scroll.viewport().width() - 24)
            self.image.setPixmap(pm.scaledToWidth(
                w, Qt.TransformationMode.SmoothTransformation))
        else:
            self.image.setText("(frame file missing)")
        dt = datetime.fromtimestamp(r["ts"]).strftime("%A %d %B %Y  %H:%M:%S")
        self.meta.setText(f"<b>{dt}</b> — <i>{r['app'] or '?'}</i><br>{r['title'] or ''}")
        self.slider.blockSignals(True)
        self.slider.setValue(idx)
        self.slider.blockSignals(False)

    def open_folder(self):
        idx = self.results.currentRow()
        target = (Path(self.rows[idx]["path"]).parent
                  if 0 <= idx < len(self.rows) else config.FRAME_DIR)
        subprocess.Popen(["xdg-open", str(target)])


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CachyRecorder")
    v = Viewer()
    v.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
