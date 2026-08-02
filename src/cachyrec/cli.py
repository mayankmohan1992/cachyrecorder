"""CachyRecorder CLI."""
import argparse
import json
import sys
import time
from datetime import datetime

from . import config, store


def cmd_status(_):
    conn = store.connect()
    s = store.stats(conn)
    cfg = config.load()
    first = (datetime.fromtimestamp(s["first_ts"]).strftime("%Y-%m-%d %H:%M")
             if s["first_ts"] else "—")
    print(f"paused        : {cfg['paused']}")
    print(f"interval      : {cfg['interval_sec']}s")
    print(f"retention     : {cfg['retention_days']} days")
    print(f"frames        : {s['total']} ({s['ocr_done']} OCR-indexed)")
    print(f"disk          : {s['bytes']/1024/1024:.1f} MB")
    print(f"oldest frame  : {first}")
    print(f"data dir      : {config.DATA_DIR}")


def cmd_search(a):
    conn = store.connect()
    rows = store.search(conn, " ".join(a.query), limit=a.limit)
    if not rows:
        print("no results")
        return
    for r in rows:
        t = datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n\033[1m{t}\033[0m  [{r['app'] or '?'}]  {r['title'] or ''}")
        print(f"  {r['path']}")
        if r["snip"]:
            print(f"  … {r['snip']}")


def cmd_pause(_):
    config.set_paused(True)
    print("paused")


def cmd_resume(_):
    config.set_paused(False)
    print("resumed")


def cmd_set(a):
    cfg = config.load()
    if a.key not in cfg:
        print(f"unknown key. valid: {', '.join(cfg)}")
        sys.exit(1)
    cur = cfg[a.key]
    val = a.value
    if isinstance(cur, bool):
        val = val.lower() in ("1", "true", "yes", "on")
    elif isinstance(cur, int):
        val = int(val)
    elif isinstance(cur, list):
        # accept either JSON (["a","b"]) or a bare comma-separated list
        try:
            parsed = json.loads(val)
            val = parsed if isinstance(parsed, list) else [str(parsed)]
        except (json.JSONDecodeError, ValueError):
            val = [x.strip() for x in val.split(",") if x.strip()]
    cfg[a.key] = val
    config.save(cfg)
    print(f"{a.key} = {val}")


def cmd_purge(a):
    conn = store.connect()
    before = store.stats(conn)
    cutoff = time.time() - a.days * 86400
    if not a.yes:
        n = conn.execute("SELECT COUNT(*) c FROM frames WHERE ts < ?",
                         (cutoff,)).fetchone()["c"]
        if not n:
            print(f"nothing older than {a.days} days")
            return
        resp = input(f"delete {n} frames older than {a.days} days? [y/N] ")
        if resp.strip().lower() not in ("y", "yes"):
            print("aborted")
            return
    store.purge_older_than(conn, cutoff)
    conn.commit()
    after = store.stats(conn)
    freed = (before["bytes"] - after["bytes"]) / 1e6
    print(f"removed {before['total'] - after['total']} frames, freed {freed:.1f} MB")


def main():
    p = argparse.ArgumentParser(prog="cachyrec", description="CachyRecorder — screen memory search")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("pause").set_defaults(fn=cmd_pause)
    sub.add_parser("resume").set_defaults(fn=cmd_resume)

    s = sub.add_parser("search")
    s.add_argument("query", nargs="+")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(fn=cmd_search)

    st = sub.add_parser("set")
    st.add_argument("key")
    st.add_argument("value")
    st.set_defaults(fn=cmd_set)

    pu = sub.add_parser("purge", help="delete frames older than N days")
    pu.add_argument("--days", type=int, required=True)
    pu.add_argument("--yes", action="store_true", help="skip confirmation")
    pu.set_defaults(fn=cmd_purge)

    g = sub.add_parser("gui")
    g.set_defaults(fn=lambda _: __import__("cachyrec.viewer", fromlist=["main"]).main())

    t = sub.add_parser("tray")
    t.set_defaults(fn=lambda _: __import__("cachyrec.tray", fromlist=["main"]).main())

    d = sub.add_parser("daemon")
    d.set_defaults(fn=lambda _: __import__("cachyrec.daemon", fromlist=["main"]).main())

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
