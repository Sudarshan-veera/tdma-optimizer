#!/usr/bin/env bash
# Host side, from the project root.  Asks YOU for the number of radios and coverage (nothing is assumed), builds the best-case
# schedule, then runs all eight advancements.  Up to MAXLIVE radios the EMANE lab is used; above that only the offline
# analysis runs (a single laptop cannot emulate that many radios with accurate slot timing).
#   ./emane/evo3_host.sh                        # asks for n and coverage
#   ./emane/evo3_host.sh results/opt_n12.json   # reuse an existing optimizer result
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
MAXLIVE=${MAXLIVE:-30}
if [ -n "${1:-}" ]; then
  JSON=$1; shift
else
  PYTHONPATH=. $PY -m tdmaopt.hetero            # interactive: number of radios, coverage, optional distance
  JSON=$(ls -t results/opt_n*.json | head -1)
fi
N=$($PY -c "import json;print(len(json.load(open('$JSON'))['layout']))")
echo "Using optimizer result: $JSON  ($N radios)"
if [ "$N" -gt "$MAXLIVE" ]; then
  OUT=results/evo3-full-$(date +%Y%m%d-%H%M%S)
  echo "$N radios > $MAXLIVE: running the offline analysis only (no EMANE)."
  PYTHONPATH=. $PY emane/evo3_full.py offline "$JSON" --out "$OUT" "$@"
  echo "Done. Report: $OUT/EVO3_FULL_REPORT.md"
  exit 0
fi
docker image inspect tdma-emane >/dev/null 2>&1 || { echo "Build the base image first: docker build -t tdma-emane -f emane/Dockerfile ."; exit 1; }
docker image inspect tdma-emane-full >/dev/null 2>&1 || docker build -t tdma-emane-full -f emane/Dockerfile.full .
docker run --rm --privileged -v "$PWD":/work -w /work -e HOST_UID=$(id -u) -e HOST_GID=$(id -g) \
  tdma-emane-full ./emane/run_evo3_full.sh "$JSON" --resilient "$@"
echo "Done. Open the newest results/evo3-full-*/EVO3_FULL_REPORT.md"
