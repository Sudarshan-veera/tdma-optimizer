# TDMA Schedule Planner and Optimizer

Vaan Megam Networks - Wireless Protocol Development internship task
**Author:** Sudarshan V (Roll No. 2023105063), College of Engineering Guindy, Anna University, Chennai
**Date:** 1 October 2026

A centralized Python "Network Brain" that takes the positions of 16 radios and produces a collision-free TDMA schedule using distance-2 (two-hop) graph colouring with spatial reuse. The schedule is converted to an EMANE TDMA schedule and exercised in an emulation (Part 2), and cross-checked with MATLAB and ns-3 slot-level simulations.

## Key results (demo grid: 4 x 4 nodes, 300 m spacing, 500 m range)

| Item | Value |
|---|---|
| Frame length | 9 slots, proven optimal (lower bound 9) |
| Radio links | 42 |
| Spatial reuse | up to 4 radios per slot (corners 01, 04, 13, 16 share slot 8) |
| Capacity gain vs token passing (16 slots) | 1.78x (9,333 vs 5,250 receptions/s at 1 ms slots) |
| Conflicts found by the independent verifier | 0 |
| Random topologies (150 layouts) | optimum proven in 150 / 150, mean 7.77 slots, 2.13x gain |
| Automated tests | 77 passing |
| Slot-level simulation (MATLAB and ns-3) | Brain schedule: 0 collisions; Node_03 forced into Node_01's slot: 8 collided receptions per frame (88.1% delivery) |
| EMANE 1.5.3, 16 NEMs | schedule accepted by every NEM checked; hidden-terminal UDP loss 6-14% with the Brain's schedule vs 30% with a colliding schedule |

The EMANE and simulation results are consistent with the colouring preventing collisions. They are small experiments on one laptop, not statistical benchmarks (see `docs/DOCUMENTATION.md`).

## Repository structure

```
tdma-optimizer/
├── tdma_brain.py            Part 1: scheduler (DSATUR + restarts + local search + exact check + verifier)
├── emane_bridge.py          Part 2: schedule.json -> EMANE schedule XML and pathloss EEL
├── benchmark_random.py      Heuristic comparison on random topologies
├── requirements.txt         networkx, matplotlib, pytest
├── Dockerfile               Part 1 container
├── tests/                   77 automated tests
├── emane/                   Part 2 test bench (Dockerfile, gen_configs.py, run_demo.sh)
├── ns3/                     ns-3.43 programs and setup notes
├── sim/                     MATLAB/Octave scripts, CSV exporter, schedule outputs
└── docs/
    ├── documentation.pdf    Submitted documentation
    ├── presentation.pptx    Submitted presentation
    ├── DOCUMENTATION.md     Full technical write-up
    ├── figures/             Plots
    └── emane-evidence/      Raw EMANE tables and iperf3 results
```

## Quick start (Part 1)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python tdma_brain.py                                  # built-in 4x4 grid
python tdma_brain.py '{"Node_01":[0.0,0.0],"Node_02":[300.0,0.0],...,"Node_16":[900.0,900.0]}'
python tdma_brain.py --json-out schedule.json --plot  # save the schedule and a plot
python -m pytest -q                                   # 77 tests
python benchmark_random.py --trials 150               # heuristic comparison
```

The CLI prints the report, the node-to-slot mapping and the Slot x Node boolean matrix, and prints "Schedule verified conflict-free" only if the independent verifier passes.

## How it works

1. Radios are nodes; two radios are linked if they are within 500 m (inclusive).
2. Two radios conflict if they are 1 hop apart (direct link) or 2 hops apart (hidden terminal). Together these are the edges of the square of the graph, so scheduling is vertex colouring of G squared; each colour is a slot.
3. DSATUR with 300 random restarts and a local search finds a colouring.
4. A lower bound (a node and its neighbours form a clique) and a time-limited exact search show whether the result is provably optimal.
5. A verifier recomputes every 1-hop and 2-hop pair from the raw coordinates using separate code.

## Part 2: EMANE

```bash
python tdma_brain.py --json-out schedule.json
python emane_bridge.py schedule.json                   # schedule.xml + scenario.eel

docker build -t tdma-emane -f emane/Dockerfile .
docker run --rm -it --privileged -e HOST_UID=$(id -u) -v "$PWD":/work -w /work \
    tdma-emane ./emane/run_demo.sh
```

The container (Ubuntu 24.04, EMANE 1.5.3) creates 16 network namespaces with one EMANE TDMA instance each, sends the Brain's schedule and a deliberately bad one, and saves tables and iperf3 results to `docs/emane-evidence/`.

## Simulations (MATLAB and ns-3)

```bash
python tdma_brain.py --json-out schedule.json
python sim/export_for_sims.py schedule.json sim/schedule_sim.csv
```

- **MATLAB (Windows):** open MATLAB, `cd` to `sim`, run `vaanmegam_task_simulation` for the full report or `tdma_sim('Csv','schedule_sim.csv')` to compare the Brain's schedule with a bad schedule, token passing and random schedules. No toolboxes needed.
- **ns-3.43 (WSL/Ubuntu):** see `ns3/README_NS3.md`. `ns3/tdma-schedule-sim.cc` is copied into ns-3's `scratch/` and run with `./ns3 run "tdma-schedule-sim --input=<path>/sim/schedule_sim.csv"`.

Both programs use the same reception rule: a reception is lost if the receiver is transmitting or if a second in-range transmitter is active in the same slot.

## Documentation

- `docs/documentation.pdf` - submitted documentation (design process, thought process, final values)
- `docs/DOCUMENTATION.md` - extended technical write-up
- `docs/presentation.pptx` - submitted presentation

## Limitations

Binary 500 m disk model (no SINR, fading or capture); static nodes; one transmit slot per node per frame; single frequency; small EMANE experiment on one machine with a timing-noise floor.

## License

MIT, see `LICENSE`.
