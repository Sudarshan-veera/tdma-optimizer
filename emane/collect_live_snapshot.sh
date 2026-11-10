#!/usr/bin/env bash
set -euo pipefail

cd /work
OUT="$1"
mkdir -p "$OUT"
OUT="$(realpath "$OUT")"
SECS=10

python3 - "$OUT/plan.json" "$SECS" <<'PY'
import json
import sys

source = "results/emane-evidence/plan.json"
plan = json.load(open(source))
seconds = int(sys.argv[2])

if len(plan["links"]) != 11:
    raise SystemExit("Expected 11 transmitting links")

for link in plan["links"]:
    pps = float(link["pps"])
    if pps <= 0:
        raise SystemExit(f"Invalid sending rate for NEM {link['nem']}")
    link["sent"] = int(pps * seconds)

with open(sys.argv[1], "w") as f:
    json.dump(plan, f, indent=2)

print("Prepared fresh probe plan:", len(plan["links"]), "senders")
PY

receiver_pids=()
sender_pids=()

cleanup() {
    for pid in "${receiver_pids[@]}" "${sender_pids[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
}
trap cleanup EXIT

echo "Starting receivers in all 12 namespaces..."

for i in $(seq 1 12); do
    ip netns exec "n$i" python3 /work/emane/udp_probe.py \
        recv "$((SECS + 6))" "$OUT/rx_$i.json" \
        > "$OUT/receiver_$i.log" 2>&1 &
    receiver_pids+=("$!")
done

sleep 1

echo "Starting fresh packet transmissions..."

while read -r nem pps; do
    ip netns exec "n$nem" python3 /work/emane/udp_probe.py \
        send "$nem" "$pps" "$SECS" \
        > "$OUT/sender_$nem.log" 2>&1 &
    sender_pids+=("$!")
done < <(python3 - "$OUT/plan.json" <<'PY'
import json
import sys

plan = json.load(open(sys.argv[1]))
for link in plan["links"]:
    print(link["nem"], link["pps"])
PY
)

for pid in "${sender_pids[@]}"; do
    wait "$pid"
done

for pid in "${receiver_pids[@]}"; do
    wait "$pid"
done

for i in $(seq 1 12); do
    test -s "$OUT/rx_$i.json" || {
        echo "Missing receiver output: rx_$i.json"
        exit 1
    }
done

echo "Fresh packet collection completed."
echo "Output directory: $OUT"
