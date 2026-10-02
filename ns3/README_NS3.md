# ns-3 Simulation Setup

This folder contains `tdma_ns3.cc`, a discrete-event simulation that verifies
the schedule from `tdma_brain.py` achieves 100% packet delivery with zero collisions.

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
