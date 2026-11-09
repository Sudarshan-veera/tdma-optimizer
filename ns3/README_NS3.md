# ns-3 Simulation Setup

This folder contains two ns-3.43 programs.

| File | What it does | Use it for |
|---|---|---|
| `tdma-schedule-sim.cc` | Implements the TDMA reception rule on ns-3 nodes, mobility models and the event scheduler, with a 500 m disk model. Runs the Brain schedule, a bad schedule, token passing, one slot and random schedules for 1000 frames. | The main ns-3 check |
| `tdma_ns3.cc` | Sends one UDP packet per link per slot over a CSMA channel. CSMA is wired and has no radio range, so it only confirms the schedule is applied slot by slot and would also report full delivery for a bad schedule. | A quick plumbing check |

Run `tdma-schedule-sim.cc` first. The sections below cover `tdma_ns3.cc`; the
section at the end covers `tdma-schedule-sim.cc`.

## Quick start (Ubuntu/WSL)

```bash
# 1. Get ns-3.43
mkdir ~/tdma-ns3 && cd ~/tdma-ns3
wget https://www.nsnam.org/releases/ns-allinone-3.43.tar.bz2
tar xjf ns-allinone-3.43.tar.bz2
cd ns-allinone-3.43/ns-3.43

# 2. Configure (add csma module)
python3 ns3 configure configure \
  --disable-examples --disable-tests \
  --enable-modules=core,network,internet,mobility,csma

# 3. Build
python3 ns3 build -j 2

# 4. Copy and compile simulation
cp /path/to/tdma-optimizer/ns3/tdma_ns3.cc scratch/
cmake --build cmake-cache --target scratch_tdma_ns3 -j 2

# 5. Run
./build/scratch/ns3.43-tdma_ns3-default
./build/scratch/ns3.43-tdma_ns3-default --csv=schedule_matlab.csv
```

## Expected output

```
=== TDMA ns-3 Simulation ===
Nodes: 16  Frame: 9 slots  Links: 42  Max RX/frame: 84

=== RESULTS ===
Frames simulated    : 10
Expected receptions : 840
Delivered           : 840
Packet delivery     : 100.00 %
Approx throughput   : 18108.6 kbps
Capacity gain vs token passing: 1.78x
===
```

## Note on Python 3.14 / Ubuntu 26.04

ns-3.43's `ns3` script has a bug with Python 3.14's `argparse`.
The subcommand word must be repeated: `python3 ns3 configure configure ...`

## Main check: tdma-schedule-sim.cc

```bash
# schedule input, from the repository root
python tdma_brain.py --json-out schedule.json
python sim/export_for_sims.py schedule.json sim/schedule_sim.csv

# in the ns-3 folder
cp /path/to/tdma-optimizer/ns3/tdma-schedule-sim.cc scratch/
cmake --build cmake-cache --target scratch_tdma-schedule-sim -j 2
./build/scratch/ns3.43-tdma-schedule-sim-default \
  --input=/path/to/tdma-optimizer/sim/schedule_sim.csv \
  --out=/path/to/tdma-optimizer/sim/ns3_results.csv
```

Expected result (1000 frames; the random row varies slightly with the seed):

```
Scenario                              Slots  Delivered   Delivery   Deliv./sec
Brain schedule                            9      84.00    100.00%         9333
Bad: Node_03 in Node_01's slot            9      74.00     88.10%         8222
Token passing (1 node per slot)          16      84.00    100.00%         5250
All nodes in one slot                     1       0.00      0.00%            0
Random schedule (mean of 200)             9      44.19     52.60%         4909

Brain schedule check: PASS - zero collisions
```
