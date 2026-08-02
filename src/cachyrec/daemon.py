"""Recorder daemon: capture loop + OCR indexing worker."""
import logging
import queue
import signal
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image

from . import capture, config, store

log = logging.getLogger("cachyrec")

_stop = threading.Event()
_ocr_q: queue.Queue = queue.Queue()


def _frame_path(ts: int) -> Path:
    dt = datetime.fromtimestamp(ts)
    d = config.FRAME_DIR / dt.strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{dt.strftime('%H%M%S')}_{ts}.webp"


def _excluded(title: str, app: str, cfg) -> bool:
    hay = f"{title} {app}".lower()
    return any(k.lower() in hay for k in cfg.get("exclude_title_keywords", []) if k.strip())


def ocr_image(path: Path, lang: str) -> str:
    try:
        r = subprocess.run(
            ["tesseract", str(path), "stdout", "-l", lang, "--psm", "6"],
            capture_output=True, text=True, timeout=90,
        )
        return " ".join(r.stdout.split())
    except Exception as e:
        log.warning("ocr failed %s: %s", path.name, e)
        return ""


def ocr_worker():
    conn = store.connect()
    while not _stop.is_set():
        cfg = config.load()
        rows = store.pending_ocr(conn, limit=8)
        if not rows:
            _stop.wait(4)
            continue
        for r in rows:
            if _stop.is_set():
                break
            p = Path(r["path"])
            text = ocr_image(p, cfg["ocr_lang"]) if p.exists() else ""
            store.save_ocr(conn, r["id"], text, r["title"], r["app"])
        time.sleep(0.2)
    conn.close()


def retention_worker():
    conn = store.connect()
    while not _stop.is_set():
        cfg = config.load()
        days = int(cfg.get("retention_days", 30))
        if days > 0:
            cutoff = int((datetime.now() - timedelta(days=days)).timestamp())
            n = store.purge_older_than(conn, cutoff)
            if n:
                log.info("purged %d expired frames", n)
        _stop.wait(3600)
    conn.close()


def capture_loop():
    conn = store.connect()
    last_hash = store.last_dhash(conn)
    while not _stop.is_set():
        cfg = config.load()
        interval = max(1, int(cfg.get("interval_sec", 5)))

        if cfg.get("paused"):
            _stop.wait(interval)
            continue
        if capture.is_locked():
            _stop.wait(interval)
            continue
        idle_limit = int(cfg.get("pause_on_idle_sec", 0))
        if idle_limit and capture.idle_seconds() > idle_limit:
            _stop.wait(interval)
            continue

        started = time.time()
        ts = int(started)
        app, title = capture.active_window()

        if _excluded(title, app, cfg):
            log.debug("skip excluded window: %s", title[:40])
            _sleep_rest(started, interval)
            continue

        tmp = Path(f"/tmp/cachyrec_{ts}.png")
        if not capture.grab_screen(tmp):
            log.warning("capture failed")
            _sleep_rest(started, interval)
            continue

        try:
            img = Image.open(tmp)
            img.load()
            h = capture.dhash(img)
            if capture.hamming(h, last_hash) < int(cfg.get("similarity_skip", 4)):
                tmp.unlink(missing_ok=True)
                _sleep_rest(started, interval)
                continue
            last_hash = h

            maxw = int(cfg.get("max_width", 1600))
            if img.width > maxw:
                img = img.resize((maxw, int(img.height * maxw / img.width)),
                                 Image.Resampling.LANCZOS)
            dest = _frame_path(ts)
            img.convert("RGB").save(dest, "WEBP", quality=int(cfg.get("webp_quality", 55)))
            store.add_frame(conn, ts, dest, title, app, h)
            log.info("frame %s (%s) %.0fkB", dest.name, app or "?", dest.stat().st_size / 1024)
        except Exception as e:
            log.error("frame processing failed: %s", e)
        finally:
            tmp.unlink(missing_ok=True)

        _sleep_rest(started, interval)
    conn.close()


def _sleep_rest(started, interval):
    rest = interval - (time.time() - started)
    if rest > 0:
        _stop.wait(rest)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: _stop.set())

    threads = [
        threading.Thread(target=ocr_worker, daemon=True, name="ocr"),
        threading.Thread(target=retention_worker, daemon=True, name="retention"),
    ]
    for t in threads:
        t.start()
    log.info("cachyrecorder daemon started (data=%s)", config.DATA_DIR)
    try:
        capture_loop()
    finally:
        _stop.set()
        log.info("stopped")


if __name__ == "__main__":
    main()
