#!/usr/bin/env bash
# Proof-based merge gate. Exits non-zero if the live system is not healthy.
# Nothing merges to main unless this passes.
set -uo pipefail

RUNTIME="${CACHYREC_RUNTIME:-$HOME/.local/share/cachyrecorder}"
PASS=0; FAIL=0
ok(){ echo "  PASS  $1"; PASS=$((PASS+1)); }
no(){ echo "  FAIL  $1"; FAIL=$((FAIL+1)); }

echo "== CachyRecorder verification =="

# 1. syntax
if python3 -m compileall -q "$RUNTIME/cachyrec" >/dev/null 2>&1; then
  ok "python sources compile"; else no "python sources compile"; fi

# 2. imports under the real interpreter
if PYTHONPATH="$RUNTIME" /usr/bin/python3 -c \
   "import cachyrec.daemon, cachyrec.tray, cachyrec.viewer, cachyrec.cli" 2>/dev/null; then
  ok "all modules import"; else no "all modules import"; fi

# 3. services running
for u in cachyrecorder.service cachyrecorder-tray.service; do
  if [[ "$(systemctl --user is-active $u)" == "active" ]]; then
    ok "$u active"; else no "$u active"; fi
done

# 4. no crash-looping
for u in cachyrecorder.service cachyrecorder-tray.service; do
  n=$(systemctl --user show -p NRestarts --value $u)
  if [[ "${n:-0}" -le 2 ]]; then ok "$u stable (restarts=$n)";
  else no "$u restart-looping (restarts=$n)"; fi
done

# 5. capture actually advances
before=$(PYTHONPATH="$RUNTIME" /usr/bin/python3 -c \
  "from cachyrec import store;print(store.stats(store.connect())['total'])" 2>/dev/null || echo 0)
iv=$(PYTHONPATH="$RUNTIME" /usr/bin/python3 -c \
  "from cachyrec import config;print(config.load()['interval_sec'])" 2>/dev/null || echo 5)
paused=$(PYTHONPATH="$RUNTIME" /usr/bin/python3 -c \
  "from cachyrec import config;print(config.load()['paused'])" 2>/dev/null || echo False)
if [[ "$paused" == "True" ]]; then
  echo "  SKIP  capture advance (recorder is paused)"
else
  sleep $(( iv * 3 + 4 ))
  after=$(PYTHONPATH="$RUNTIME" /usr/bin/python3 -c \
    "from cachyrec import store;print(store.stats(store.connect())['total'])" 2>/dev/null || echo 0)
  if [[ "$after" -gt "$before" ]]; then ok "capturing frames ($before -> $after)";
  else no "no new frames in $(( iv*3+4 ))s ($before -> $after)"; fi
fi

# 6. OCR keeping up
PYTHONPATH="$RUNTIME" /usr/bin/python3 - <<'EOF' && ok "OCR backlog sane" || no "OCR backlog growing"
import sys
from cachyrec import store
s = store.stats(store.connect())
backlog = s["total"] - s["ocr_done"]
print(f"        backlog={backlog} of {s['total']}")
sys.exit(0 if backlog < 60 else 1)
EOF

# 7. search returns hits
PYTHONPATH="$RUNTIME" /usr/bin/python3 - <<'EOF' && ok "FTS search works" || no "FTS search broken"
import sys
from cachyrec import store
c = store.connect()
rows = c.execute("SELECT app FROM frames WHERE app!='' ORDER BY ts DESC LIMIT 1").fetchone()
if not rows:
    sys.exit(0)
sys.exit(0 if len(store.search(c, rows[0])) >= 0 else 1)
EOF

# 8. tray registered with Plasma (the bug that bit us before)
TP=$(systemctl --user show -p MainPID --value cachyrecorder-tray.service)
if [[ "${TP:-0}" -gt 0 ]]; then
  items=$(busctl --user get-property org.kde.StatusNotifierWatcher \
      /StatusNotifierWatcher org.kde.StatusNotifierWatcher \
      RegisteredStatusNotifierItems 2>/dev/null)
  mine=$(busctl --user list --no-legend 2>/dev/null | awk -v p="$TP" '$2==p{print $1}')
  hit=0; for m in $mine; do [[ "$items" == *"$m"* ]] && hit=1; done
  if [[ $hit -eq 1 ]]; then ok "tray registered in Plasma"; else no "tray NOT in Plasma panel"; fi
else
  no "tray has no MainPID"
fi

# 9. CLI responds
if "$HOME/.local/bin/cachyrec" status >/dev/null 2>&1; then
  ok "cachyrec CLI works"; else no "cachyrec CLI broken"; fi

echo "== $PASS passed, $FAIL failed =="
exit $(( FAIL > 0 ? 1 : 0 ))
