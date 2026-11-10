#!/usr/bin/env bash
set -euo pipefail

cd /work

OUT="$1"
SEND_SECONDS=10
RUN_SECONDS=22

mkdir -p "$OUT"

cp results/emane-evidence/plan.json "$OUT/plan.json"

relay_pids=()
sender_pids=()
sink_pid=""

cleanup() {
    for pid in "${sender_pids[@]}" "${relay_pids[@]}" "$sink_pid"; do
        if [[ -n "$pid" ]]; then
            kill "$pid" 2>/dev/null || true
        fi
    done
}
trap cleanup EXIT

echo "Starting gateway sink..."

ip netns exec n1 python3 /work/emane/multihop_probe.py \
    sink --seconds "$RUN_SECONDS" \
    --out "$OUT/multihop_report.json" \
    > "$OUT/sink.log" 2>&1 &
sink_pid=$!

echo "Starting forwarding relays..."

for pair in "2 1" "5 2" "6 5"; do
    read -r nem parent <<< "$pair"

    ip netns exec "n$nem" python3 /work/emane/multihop_probe.py \
        relay --nem "$nem" --parent "$parent" \
        --seconds "$RUN_SECONDS" \
        > "$OUT/relay_$nem.log" 2>&1 &

    relay_pids+=("$!")
done

sleep 2

echo "Starting 11 packet sources..."

while read -r nem parent pps; do
    ip netns exec "n$nem" python3 /work/emane/multihop_probe.py \
        send --nem "$nem" --parent "$parent" \
        --pps "$pps" --seconds "$SEND_SECONDS" \
        > "$OUT/sender_$nem.log" 2>&1 &

    sender_pids+=("$!")
done < <(python3 - "$OUT/plan.json" <<'PY'
import json
import sys

plan = json.load(open(sys.argv[1]))

for link in plan["links"]:
    print(link["nem"], link["parent"], link["pps"])
PY
)

for pid in "${sender_pids[@]}"; do
    wait "$pid"
done

echo "All senders completed. Waiting for sink and relays..."

for pid in "${relay_pids[@]}"; do
    wait "$pid"
done

wait "$sink_pid"
sink_pid=""

echo
echo "========== MULTI-HOP RESULTS =========="

python3 - "$OUT" "$SEND_SECONDS" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
seconds = int(sys.argv[2])

plan = json.loads((out / "plan.json").read_text())
report = json.loads((out / "multihop_report.json").read_text())

parents = {
    int(x["nem"]): int(x["parent"])
    for x in plan["links"]
}

expected = {}

for nem, parent in parents.items():
    count = next(int(float(x["pps"]) * seconds)
                 for x in plan["links"] if int(x["nem"]) == nem)

    path = [nem]
    current = parent

    while current != 1:
        path.append(current)
        current = parents[current]

    expected[nem] = {
        "sent": count,
        "path": path
    }

print(f"{'NEM':<6}{'Sent':<8}{'Received':<11}{'PDR':<12}{'Hops':<7}Path")

total_sent = 0
total_received = 0
path_errors = []

for nem in sorted(expected):
    sent = expected[nem]["sent"]
    item = report.get(str(nem), {})
    received = int(item.get("received_unique", 0))
    pdr = received / sent if sent else 0
    actual_path = item.get("last_path", [])
    expected_path = expected[nem]["path"]

    total_sent += sent
    total_received += received

    hops = item.get("mean_hops", 0)

    print(
        f"{nem:<6}{sent:<8}{received:<11}"
        f"{pdr:<12.2%}{hops:<7.1f}{actual_path}"
    )

    if actual_path and actual_path != expected_path:
        path_errors.append(
            (nem, expected_path, actual_path)
        )

missing = sorted(set(map(str, expected)) - set(report))

print("\nTotal received:", total_received, "/", total_sent)
print("Overall PDR:",
      f"{total_received / total_sent:.2%}" if total_sent else "N/A")

print("Missing origins:", missing)
print("Unexpected route paths:", path_errors)

result = {
    "expected_routes": expected,
    "received": report,
    "total_sent": total_sent,
    "total_received": total_received,
    "overall_pdr": total_received / total_sent if total_sent else 0,
    "missing_origins": missing,
    "route_errors": path_errors
}

(out / "multihop_summary.json").write_text(
    json.dumps(result, indent=2)
)

print("\nSaved:", out / "multihop_summary.json")

if missing or path_errors:
    raise SystemExit("MULTI-HOP VALIDATION NEEDS INVESTIGATION")

print("\nMULTI-HOP ROUTE VALIDATION PASSED")
PY

echo
echo "Relay forwarding counts:"
for file in "$OUT"/relay_*.log; do
    echo "$file"
    cat "$file"
done

echo "Experiment completed: $OUT"
