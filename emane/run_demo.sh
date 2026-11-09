#!/usr/bin/env bash
# Part 2 demo. Run INSIDE the tdma-emane container (needs --privileged), from the repo root.
#   ./emane/run_demo.sh            # full run: good, bad, good-again, evidence saved
#   ./emane/run_demo.sh down       # tear everything down
set -uo pipefail
N=16
OUT=/tmp/emane-run
EVID=/work/docs/emane-evidence
cd "$(dirname "$0")/.."

down() {
  pkill emaneeventservice 2>/dev/null; pkill -x emane 2>/dev/null; pkill iperf3 2>/dev/null
  for i in $(seq 1 $N); do ip netns del n$i 2>/dev/null; ip link del v$i 2>/dev/null; done
  ip link del br0 2>/dev/null
  return 0
}
[ "${1:-}" = "down" ] && { down; echo "cleaned up"; exit 0; }
down; rm -rf "$OUT" "$EVID"; mkdir -p "$OUT" "$EVID"

echo "== 1. Brain -> schedule.json -> EMANE configs"
python3 tdma_brain.py --json-out "$OUT/schedule.json" | tee "$EVID/brain_output.txt" | sed -n '1,9p'
python3 emane/gen_configs.py "$OUT/schedule.json" --out "$OUT" || exit 1
cp "$OUT"/schedule_good.xml "$OUT"/schedule_bad.xml "$EVID"/

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
sleep 4
for i in 1 2 16; do ip netns exec n$i ip -br addr show emane0 2>&1 | head -1; done
if ! ip netns exec n1 ip link show emane0 >/dev/null 2>&1; then
  echo "!! emane0 not created. Last log lines:"; tail -n 15 "$OUT/emane1.log"; exit 1
fi

echo "== 4. Pathloss events (500 m range model) from scenario.eel"
(cd "$OUT" && emaneeventservice -d -l 3 -f "$OUT/eventservice.log" eventservice.xml)
sleep 4

stats() { for i in 1 2 3 16; do echo "-- NEM $i"; emanesh 192.168.77.$i get stat nems mac 2>&1 | grep -i "scheduler\.scheduleAccept\|scheduler\.scheduleReject.*[1-9]$" ; done; }

# collision probe: 01 and 03 are 600 m apart (not neighbours) but both hear 02 -> hidden terminals.
# A correct schedule must never let them transmit in the same slot.
run_phase() {   # $1 = label, $2 = schedule file (good|bad)
  local tag=$1 sched=$2
  echo; echo "================ $tag  (schedule_$sched.xml) ================"
  emaneevent-tdmaschedule "$OUT/schedule_$sched.xml" -i br0
  sleep 3
  stats | tee "$EVID/${tag}_schedule_stats.txt"
  emanesh 192.168.77.1 get table nems mac scheduler.ScheduleInfoTable scheduler.StructureInfoTable \
      > "$EVID/${tag}_nem1_schedule_tables.txt" 2>&1
  echo "-- warm-up (ARP + queues), not counted"
  ip netns exec n1 ping -c 4 -W 2 10.100.0.2 >/dev/null 2>&1
  ip netns exec n3 ping -c 4 -W 2 10.100.0.2 >/dev/null 2>&1
  echo "-- reachability (5 pings each)"
  {
    echo "01 -> 02 (300 m, in range):";  ip netns exec n1 ping -c 5 -W 2 10.100.0.2  | tail -2
    echo "01 -> 16 (1273 m, out of range, expect 100% loss):"; ip netns exec n1 ping -c 5 -W 2 10.100.0.16 | tail -2
  } | tee "$EVID/${tag}_ping.txt"
  echo "-- collision probe: 01 and 03 both send 1000-byte UDP at 200 kbit/s to 02 for 15 s"
  ip netns exec n2 iperf3 -s -p 5201 -D; ip netns exec n2 iperf3 -s -p 5202 -D
  sleep 1
  ip netns exec n1 iperf3 -u -l 1000 -c 10.100.0.2 -p 5201 -b 200k -t 15 > "$OUT/iperf_01.txt" 2>&1 &
  ip netns exec n3 iperf3 -u -l 1000 -c 10.100.0.2 -p 5202 -b 200k -t 15 > "$OUT/iperf_03.txt" 2>&1 &
  wait
  {
    echo "01->02:"; grep -E "receiver|error|unable" "$OUT/iperf_01.txt"
    echo "03->02:"; grep -E "receiver|error|unable" "$OUT/iperf_03.txt"
  } | tee "$EVID/${tag}_udp_loss.txt"
  # raw evidence for the report: how NEM 2 saw those frames, and how well timing held
  emanesh 192.168.77.2 get table nems mac RxSlotStatusTable        > "$EVID/${tag}_nem2_rxslots.txt" 2>&1
  emanesh 192.168.77.1 get table nems mac TxSlotStatusTable        > "$EVID/${tag}_nem1_txslots.txt" 2>&1
  emanesh 192.168.77.2 get stat  nems mac                          > "$EVID/${tag}_nem2_mac_stats.txt" 2>&1
  emanesh 192.168.77.2 get table nems phy BroadcastPacketAcceptTable0 > "$EVID/${tag}_nem2_phy_accept.txt" 2>&1
  emanesh 192.168.77.2 get table nems phy BroadcastPacketDropTable0   > "$EVID/${tag}_nem2_phy_drop.txt" 2>&1
  pkill iperf3; sleep 2
}

run_phase "good"       good
run_phase "bad"        bad
run_phase "good_again" good

echo; echo "================ SUMMARY (UDP loss at Node_02) ================"
for t in good bad good_again; do
  echo "[$t]"; grep -E "receiver" "$EVID/${t}_udp_loss.txt" | sed 's/^/   /'
done
echo; echo "Evidence saved in $EVID"
[ -n "${HOST_UID:-}" ] && chown -R "$HOST_UID" "$EVID"
echo "Run './emane/run_demo.sh down' when finished."
