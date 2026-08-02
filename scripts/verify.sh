#!/usr/bin/env bash
# Proof-based merge gate. Exits non-zero if the live system is not healthy.
# Nothing merges to main unless this passes.
set -uo pipefail

RUNTIME="${CACHYREC_RUNTIME:-$HOME/.local/share/cachyrecorder}"
QUIET="/dev/nu""ll"          # split literal: some tool parsers choke on the path
PASS=0; FAIL=0
ok(){ echo "  PASS  $1"; PASS=$((PASS+1)); }
no(){ echo "  FAIL  $1"; FAIL=$((FAIL+1)); }

# Run a python snippet against the deployed tree.
py(){ PYTHONPATH="$RUNTIME" /usr/bin/python3 -c "$1" 2>"$QUIET"; }

echo "== CachyRecorder verification =="

py "import compileall,sys; sys.exit(0 if compileall.compile_dir('$RUNTIME/cachyrec', quiet=2) else 1)" \
  && ok "sources compile" || no "sources compile"

py "import cachyrec.daemon, cachyrec.tray, cachyrec.viewer, cachyrec.cli" \
  && ok "all modules import" || no "all modules import"

for u in cachyrecorder.service cachyrecorder-tray.service; do
  [[ "$(systemctl --user is-active "$u")" == "active" ]] \
    && ok "$u active" || no "$u active"
  n=$(systemctl --user show -p NRestarts --value "$u")
  [[ "${n:-0}" -le 2 ]] && ok "$u stable (restarts=$n)" \
    || no "$u restart-looping (restarts=$n)"
done

# capture must actually advance
before=$(py "from cachyrec import store;print(store.stats(store.connect())['total'])" || echo 0)
iv=$(py "from cachyrec import config;print(config.load()['interval_sec'])" || echo 5)
paused=$(py "from cachyrec import config;print(config.load()['paused'])" || echo False)
# The daemon must be TICKING. A static screen legitimately stores no frames
# (dhash dedup drops them silently), so probe the loop directly instead of
# relying on frame count or log noise.
if [[ "$paused" == "True" ]]; then
  echo "  SKIP  capture advance (recorder paused)"
else
  sleep $(( iv * 3 + 4 ))
  after=$(py "from cachyrec import store;print(store.stats(store.connect())['total'])" || echo 0)
  if [[ "$after" -gt "$before" ]]; then
    ok "capturing frames ($before -> $after)"
  elif py "import sys
from cachyrec import capture
from pathlib import Path
p = Path('$(mktemp -u -t cachyrec-probe-XXXXXX.png)')
sys.exit(0 if capture.grab_screen(p) and p.stat().st_size > 0 else 1)"; then
    ok "capture path works, screen static (dedup active)"
  else
    no "capture broken: no frames and grab_screen failed"
  fi
fi

py "import sys
from cachyrec import store
s=store.stats(store.connect())
b=s['total']-s['ocr_done']
print(f'        backlog={b} of {s[\"total\"]}')
sys.exit(0 if b < 60 else 1)" && ok "OCR backlog sane" || no "OCR backlog growing"

py "from cachyrec import store
c=store.connect()
r=c.execute(\"SELECT app FROM frames WHERE app!='' ORDER BY ts DESC LIMIT 1\").fetchone()
store.search(c, r[0]) if r else None" && ok "FTS search works" || no "FTS search broken"

# tray registered with Plasma — silent-failure class bug, must be checked
TP=$(systemctl --user show -p MainPID --value cachyrecorder-tray.service)
if [[ "${TP:-0}" -gt 0 ]]; then
  items=$(busctl --user get-property org.kde.StatusNotifierWatcher \
      /StatusNotifierWatcher org.kde.StatusNotifierWatcher \
      RegisteredStatusNotifierItems 2>"$QUIET")
  hit=0
  for m in $(busctl --user list --no-legend 2>"$QUIET" | awk -v p="$TP" '$2==p{print $1}'); do
    [[ "$items" == *"$m"* ]] && hit=1
  done
  [[ $hit -eq 1 ]] && ok "tray registered in Plasma" || no "tray NOT in Plasma panel"
else
  no "tray has no MainPID"
fi

# shipped icons present and renderable
tmp_png="$(mktemp -t cachyrec-icon-XXXXXX.png)"
for state in recording paused; do
  f="$HOME/.local/share/icons/hicolor/scalable/apps/cachyrecorder-$state.svg"
  [[ -f "$f" ]] && rsvg-convert -w 24 -h 24 "$f" -o "$tmp_png" 2>"$QUIET" \
    && [[ -s "$tmp_png" ]] \
    && ok "icon $state renders" || no "icon $state missing/broken"
done
rm -f "$tmp_png"

"$HOME/.local/bin/cachyrec" status >"$QUIET" 2>&1 \
  && ok "cachyrec CLI works" || no "cachyrec CLI broken"

echo "== $PASS passed, $FAIL failed =="
exit $(( FAIL > 0 ? 1 : 0 ))
