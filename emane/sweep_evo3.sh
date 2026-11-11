#!/usr/bin/env bash
# Long threshold sweep of Evolution 3 on EMANE.  Run INSIDE the tdma-emane container (--privileged), from the project root.
#   LOADS="0.2 0.4 0.6 0.8 1.0" REPS=5 SECS=45 ./emane/sweep_evo3.sh results/opt_n12.json
#   ./emane/sweep_evo3.sh down results/opt_n12.json
# For every offered load (fraction of each radio's slot capacity) it runs REPS rounds of: good schedule, then bad schedule.
# Every trial is appended to results/emane-sweep/sweep.csv as soon as it finishes, so a stop never loses finished work.
set -uo pipefail
cd "$(dirname "$0")/.."
if [ "${1:-}" = "down" ]; then JSON=${2:?json}; DOWN=1; else JSON=${1:?usage: sweep_evo3.sh results/opt_nN.json}; DOWN=0; fi
LOADS=${LOADS:-"0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1.0"}
REPS=${REPS:-5}
SECS=${SECS:-45}
OUT=/tmp/emane-sweep
RES=results/emane-sweep
CSV=$RES/sweep.csv
N=$(python3 -c "import json;print(len(json.load(open('$JSON'))['layout']))")

down() {
  pkill -f emaneeventservice 2>/dev/null; pkill -x emane 2>/dev/null; pkill -f udp_probe 2>/dev/null
  for i in $(seq 1 $N); do ip netns del n$i 2>/dev/null; ip link del v$i 2>/dev/null; done
  ip link del br0 2>/dev/null
  return 0
}
[ $DOWN = 1 ] && { down; echo "cleaned up"; exit 0; }
down; rm -rf "$OUT"; mkdir -p "$OUT" "$RES"

NL=$(echo $LOADS | wc -w); TOTAL=$((NL*REPS*2)); PER=$((SECS+13))
echo "== Sweep: $N radios, loads [$LOADS], $REPS reps, ${SECS}s probes, $TOTAL trials, about $((TOTAL*PER/60)) minutes"
python3 emane/gen_evo3.py "$JSON" --out "$OUT" --secs $SECS || exit 1
cp "$OUT"/schedule_good.xml "$OUT"/schedule_bad.xml "$OUT"/plan.json "$RES"/

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
for i in $(seq 1 $N); do
  (cd "$OUT" && ip netns exec n$i emane -d -r -l 3 -f "$OUT/emane$i.log" "platform-$i.xml")
done
sleep 5
if ! ip netns exec n1 ip link show emane0 >/dev/null 2>&1; then
  echo "!! emane0 not created"; tail -n 15 "$OUT/emane1.log"; exit 1
fi
(cd "$OUT" && emaneeventservice -d -l 3 -f "$OUT/eventservice.log" eventservice.xml)
sleep 4

trial() {   # $1 load  $2 rep  $3 good|bad
  local d="$OUT/t_$1_$2_$3"
  mkdir -p "$d"
  python3 emane/sweep_collect.py plan "$OUT/plan.json" "$1" $SECS "$d/plan.json"
  emaneevent-tdmaschedule "$OUT/schedule_$3.xml" -i br0
  sleep 3
  for i in $(seq 1 $N); do
    ip netns exec n$i python3 emane/udp_probe.py recv $((SECS+8)) "$d/rx_$i.json" &
  done
  sleep 2
  while read -r nem pps; do
    ip netns exec n$nem python3 emane/udp_probe.py send $nem $pps $SECS >/dev/null &
  done < <(python3 -c "import json;[print(l['nem'],l['pps']) for l in json.load(open('$d/plan.json'))['links']]")
  wait
  python3 emane/sweep_collect.py collect "$d/plan.json" "$d" "$CSV" "$1" "$2" "$3"
  rm -rf "$d"
}

k=0
for load in $LOADS; do
  for rep in $(seq 1 $REPS); do
    for sched in good bad; do
      k=$((k+1)); echo "[$k/$TOTAL] $(date +%H:%M:%S)"
      trial "$load" "$rep" "$sched"
    done
  done
done
echo; echo "Sweep finished. Data: $CSV"
[ -n "${HOST_UID:-}" ] && chown -R "$HOST_UID" "$RES"
echo "Next, on the host:  python3 emane/sweep_summary.py $CSV"
