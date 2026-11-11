#!/usr/bin/env bash
# Run INSIDE the tdma-emane-full container (--privileged), from the project root:
#   ./emane/run_evo3_full.sh results/opt_nN.json [extra evo3_full.py options, e.g. --resilient --windows 4 --secs 12]
# 1) baseline good / bad / good schedules on EMANE (evidence), 2) all eight advancements on the same topology, 3) cleanup.
set -uo pipefail
cd "$(dirname "$0")/.."
JSON=${1:?usage: run_evo3_full.sh results/opt_nN.json [options]}; shift
STAMP=${STAMP:-$(date +%Y%m%d-%H%M%S)}
OUT=results/evo3-full-$STAMP
mkdir -p "$OUT"
echo "== 1/3 baseline: optimizer schedule (good), forced collision (bad), good again"
./emane/run_evo3.sh "$JSON" 2>&1 | tee "$OUT/baseline.log"
cp -r results/emane-evidence "$OUT/baseline-evidence" 2>/dev/null
echo "== 2/3 eight advancements on the same lab"
python3 emane/evo3_full.py all "$JSON" --out "$OUT" "$@" 2>&1 | tee "$OUT/advancements.log"
rc=${PIPESTATUS[0]}
echo "== 3/3 cleanup"
./emane/run_evo3.sh down "$JSON"
[ -n "${HOST_UID:-}" ] && chown -R "$HOST_UID:${HOST_GID:-$HOST_UID}" results
echo "Report: $OUT/EVO3_FULL_REPORT.md   (exit code $rc)"
exit $rc
