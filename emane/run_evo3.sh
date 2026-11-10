#!/usr/bin/env bash
# Run Evolution 3's schedule on EMANE.  Run INSIDE the tdma-emane container (--privileged), from the project root.
#   ./emane/run_evo3.sh results/opt_n12.json       # good, bad, good-again; evidence in results/emane-evidence/
#   ./emane/run_evo3.sh down results/opt_n12.json  # tear everything down
set -uo pipefail
cd "$(dirname "$0")/.."
if [ "${1:-}" = "down" ]; then JSON=${2:?json}; DOWN=1; else JSON=${1:?usage: run_evo3.sh results/opt_nN.json}; DOWN=0; fi
OUT=/tmp/emane-evo3
EVID=results/emane-evidence
SECS=15
N=$(python3 -c "import json;print(len(json.load(open('$JSON'))['layout']))")

down() {
  pkill emaneeventservice 2>/dev/null; pkill -x emane 2>/dev/null; pkill -f udp_probe 2>/dev/null
  for i in $(seq 1 $N); do ip netns del n$i 2>/dev/null; ip link del v$i 2>/dev/null; done
  ip link del br0 2>/dev/null
  return 0
}
[ $DOWN = 1 ] && { down; echo "cleaned up"; exit 0; }
down; rm -rf "$OUT" "$EVID"; mkdir -p "$OUT" "$EVID"

echo "== 1. Evolution 3 result -> EMANE configs ($N radios)"
python3 emane/gen_evo3.py "$JSON" --out "$OUT" --secs $SECS || exit 1
cp "$OUT"/schedule_good.xml "$OUT"/schedule_bad.xml "$OUT"/plan.json "$EVID"/

echo "== 2. Virtual lab: bridge br0 + one network namespace per radio"
ip link add br0 type bridge
ip link set br0 type bridge mcast_snooping 0 2>/dev/null
ip addr add 192.168.77.254/24 dev br0; ip link set br0 up
ip route add 224.0.0.0/4 dev br0 2>/dev/null
for i in $(seq 1 $N); do
  ip netns add n$i
  ip link add v$i type veth peer name eth0 netns n$i
  ip link set v$i master br0; ip link set v$i up
  ip netns exec n$i ip addr add 192.168.77.$i/24 dev eth0
  ip netns exec n$i ip link set eth0 up
  ip netns exec n$i ip link set lo up
  ip netns exec n$i ip route add 224.0.0.0/4 dev eth0 2>/dev/null
done

echo "== 3. Start $N EMANE instances (TDMA radio model, one NEM each)"
for i in $(seq 1 $N); do
  (cd "$OUT" && ip netns exec n$i emane -d -r -l 3 -f "$OUT/emane$i.log" "platform-$i.xml")
done
sleep 5
if ! ip netns exec n1 ip link show emane0 >/dev/null 2>&1; then
  echo "!! emane0 not created. Last log lines:"; tail -n 15 "$OUT/emane1.log"; exit 1
fi

echo "== 4. Pathloss events from the optimizer's ranges"
(cd "$OUT" && emaneeventservice -d -l 3 -f "$OUT/eventservice.log" eventservice.xml)
sleep 4

run_phase() {   # $1 = label, $2 = good|bad
  local tag=$1 sched=$2 d="$OUT/$1"
  mkdir -p "$d"
  echo; echo "================ $tag  (schedule_$sched.xml) ================"
  emaneevent-tdmaschedule "$OUT/schedule_$sched.xml" -i br0
  sleep 3
  emanesh 192.168.77.1 get table nems mac scheduler.ScheduleInfoTable scheduler.StructureInfoTable \
      > "$EVID/${tag}_nem1_schedule_tables.txt" 2>&1
  for i in $(seq 1 $N); do
    ip netns exec n$i python3 emane/udp_probe.py recv $((SECS+6)) "$d/rx_$i.json" &
  done
  sleep 2
  while read -r nem pps; do
    ip netns exec n$nem python3 emane/udp_probe.py send $nem $pps $SECS >/dev/null &
  done < <(python3 -c "import json;[print(l['nem'],l['pps']) for l in json.load(open('$OUT/plan.json'))['links']]")
  wait
  python3 emane/evo3_report.py "$OUT/plan.json" "$d" "$tag" | tee "$EVID/${tag}_delivery.txt"
  emanesh 192.168.77.1 get stat nems mac > "$EVID/${tag}_nem1_mac_stats.txt" 2>&1
}

run_phase good good
run_phase bad bad
run_phase good_again good

echo; echo "Evidence saved in $EVID"
[ -n "${HOST_UID:-}" ] && chown -R "$HOST_UID" "$EVID"
echo "Run './emane/run_evo3.sh down $JSON' when finished."
