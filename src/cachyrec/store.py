"""SQLite FTS5-backed frame index."""
import contextlib
import sqlite3
import time
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS frames (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        INTEGER NOT NULL,
    path      TEXT NOT NULL UNIQUE,
    title     TEXT,
    app       TEXT,
    dhash     TEXT,
    ocr_done  INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_frames_ts ON frames(ts);
CREATE INDEX IF NOT EXISTS idx_frames_ocr ON frames(ocr_done);

CREATE VIRTUAL TABLE IF NOT EXISTS frames_fts USING fts5(
    text, title, app
);
CREATE TABLE IF NOT EXISTS fts_map (
    rowid INTEGER PRIMARY KEY,
    frame_id INTEGER NOT NULL
);
"""


def connect(retries: int = 10):
    """Open a connection. WAL setup is retried: concurrent first-time
    openers can otherwise collide on the journal-mode switch."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(retries):
        conn = sqlite3.connect(config.DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(SCHEMA)
            return conn
        except sqlite3.OperationalError as e:
            last = e
            conn.close()
            time.sleep(0.3 * (attempt + 1))
    raise last


def add_frame(conn, ts, path, title, app, dhash):
    cur = conn.execute(
        "INSERT OR IGNORE INTO frames(ts,path,title,app,dhash) VALUES(?,?,?,?,?)",
        (ts, str(path), title, app, dhash),
    )
    conn.commit()
    return cur.lastrowid


def pending_ocr(conn, limit=20):
    return conn.execute(
        "SELECT * FROM frames WHERE ocr_done=0 ORDER BY ts ASC LIMIT ?", (limit,)
    ).fetchall()


def save_ocr(conn, frame_id, text, title, app):
    cur = conn.execute(
        "INSERT INTO frames_fts(text,title,app) VALUES(?,?,?)",
        (text or "", title or "", app or ""),
    )
    conn.execute("INSERT OR REPLACE INTO fts_map(rowid,frame_id) VALUES(?,?)",
                 (cur.lastrowid, frame_id))
    conn.execute("UPDATE frames SET ocr_done=1 WHERE id=?", (frame_id,))
    conn.commit()


def last_dhash(conn):
    r = conn.execute("SELECT dhash FROM frames ORDER BY ts DESC LIMIT 1").fetchone()
    return r["dhash"] if r else None


def search(conn, query, limit=300):
    """Full-text search. Returns frame rows with a snippet."""
    q = query.strip()
    if not q:
        return []
    # quote bare terms so punctuation doesn't break FTS5 syntax
    if not any(ch in q for ch in '"*') and " OR " not in q and " AND " not in q:
        q = " ".join(f'"{t}"*' for t in q.split())
    sql = """
    SELECT f.*, snippet(frames_fts,0,'[',']','…',12) AS snip
    FROM frames_fts
    JOIN fts_map m ON m.rowid = frames_fts.rowid
    JOIN frames f  ON f.id = m.frame_id
    WHERE frames_fts MATCH ?
    ORDER BY f.ts DESC LIMIT ?
    """
    try:
        return conn.execute(sql, (q, limit)).fetchall()
    except sqlite3.OperationalError:
        return []


def range_frames(conn, start_ts, end_ts, limit=2000):
    return conn.execute(
        "SELECT * FROM frames WHERE ts BETWEEN ? AND ? ORDER BY ts ASC LIMIT ?",
        (start_ts, end_ts, limit),
    ).fetchall()


def stats(conn):
    total = conn.execute("SELECT COUNT(*) c FROM frames").fetchone()["c"]
    done = conn.execute("SELECT COUNT(*) c FROM frames WHERE ocr_done=1").fetchone()["c"]
    first = conn.execute("SELECT MIN(ts) t FROM frames").fetchone()["t"]
    size = (sum(p.stat().st_size for p in config.FRAME_DIR.rglob("*.webp"))
            if config.FRAME_DIR.exists() else 0)
    return {"total": total, "ocr_done": done, "first_ts": first, "bytes": size}


def purge_older_than(conn, cutoff_ts):
    rows = conn.execute("SELECT id,path FROM frames WHERE ts < ?", (cutoff_ts,)).fetchall()
    for r in rows:
        with contextlib.suppress(OSError):
            Path(r["path"]).unlink(missing_ok=True)
        conn.execute("DELETE FROM frames_fts WHERE rowid IN "
                     "(SELECT rowid FROM fts_map WHERE frame_id=?)", (r["id"],))
        conn.execute("DELETE FROM fts_map WHERE frame_id=?", (r["id"],))
    conn.execute("DELETE FROM frames WHERE ts < ?", (cutoff_ts,))
    conn.commit()
    return len(rows)
