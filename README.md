# TDMA Schedule Optimizer ("Network Brain") + EMANE bridge

Collision-free TDMA slot scheduling for radio networks using **distance-2 graph colouring**,
with **spatial reuse** and a **provable optimality check**.

## Quick start (Ubuntu / WSL)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 tdma_brain.py                       # 4x4 demo grid (Node_01=(0,0) ... Node_16=(900,900))
python3 tdma_brain.py '{"Node_01":[0.0,0.0],"Node_02":[300.0,0.0], ... ,"Node_16":[900.0,900.0]}'
python3 tdma_brain.py --file coords.json --benchmark --plot --json-out schedule.json
python3 -m pytest -q                        # 76 tests
python3 benchmark_random.py                 # heuristic comparison on random topologies
```
Useful flags: `--range 500` `--restarts 300` `--seed 42` `--exact-time 5` `--show` (plot window via WSLg).
Docker: `docker build -t tdma . && docker run --rm tdma`

## Model
* Radios = nodes of a `networkx.Graph`; link if Euclidean distance <= 500 m (inclusive).
* Conflict if two radios are **1 hop** apart (direct link) or **share a neighbour** (hidden terminal, 2 hops).
* This equals ordinary colouring of G^2. Colour = slot. Radios > 2 hops apart reuse slots (spatial reuse).

## Algorithm
1. **DSATUR** (colour the most constrained node first) + **random restarts** + **local search**
   that tries to eliminate the highest slot.
2. **Lower bound**: maximum clique of G^2 (a node plus all its radio neighbours is always a clique).
3. **Exact branch & bound** (time-limited) to prove optimality when the heuristic is above the bound.
4. **Independent verifier** recomputes every 1-hop and 2-hop pair from the raw coordinates.

## Results
| Scenario | Slots | Notes |
|---|---|---|
| 4x4 grid, 300 m spacing | 9 | proven optimal (= lower bound); 16 slots for one-node-per-slot |
| 150 random 16-node topologies | mean 7.77 | optimum proven in 150/150; mean capacity gain 2.13x |
| 80 random nodes (3 km square) | 13 | proven optimal in 0.5 s |

On 16 nodes every heuristic lands within about 1 slot of optimal (see `benchmark_random.py`);
the exact step is what turns "good" into "proven".

## Part 2: EMANE
`emane_bridge.py schedule.json` writes `schedule.xml` (EMANE TDMA full schedule: 1 frame, 1000 us slots,
`nodes='1,4,13,16'` = spatial reuse) and `scenario.eel` (pathloss: 80 dB in range, 200 dB out of range,
so EMANE matches the 500 m model).

### Run it (Docker, EMANE 1.5.3 on Ubuntu 24.04)
```bash
docker build -t tdma-emane -f emane/Dockerfile .
docker run --rm -it --privileged -e HOST_UID=$(id -u) -v "$PWD":/work -w /work tdma-emane ./emane/run_demo.sh
```
`emane/run_demo.sh` builds a bridge + 16 network namespaces (one radio each), starts 16 EMANE TDMA
instances, loads the pathloss scenario, sends the Brain's schedule with `emaneevent-tdmaschedule`,
then runs ping and a two-sender UDP test against Node_02. It repeats with `schedule_bad.xml`
(Node_03 forced into Node_01's slot = hidden terminal) as a negative control.
Output and evidence land in `docs/emane-evidence/`.

**Status (executed):** run on EMANE 1.5.3 (Ubuntu 24.04 container on a WSL2 host), 16 NEMs, one network namespace each, TDMA radio model, 1 ms slots, 9-slot frame from the Brain. Results:
* Every NEM checked (1, 2, 3, 16) accepted the schedule (`scheduler.scheduleAcceptFull` incremented, zero rejects).
* The pathloss scenario enforced the 500 m model: Node_01 to Node_02 (300 m) reachable, Node_01 to Node_16 (1273 m) 100% loss in every run.
* Negative control (final run): UDP from Node_01 and Node_03 (hidden terminals around Node_02) lost 6-14% with the Brain's schedule and 30% when Node_03 was forced into Node_01's slot (the Node_03 flow did not complete in that case).
* Limitations: one laptop, 1 ms slots, a few runs; timing noise gives a loss floor, so this shows the schedule is consistent with collision avoidance, not a quantitative benchmark. Ping loss is too noisy to use. Raw tables are in `docs/emane-evidence/`.

## Layout
`tdma_brain.py` Brain/CLI | `emane_bridge.py` EMANE glue | `emane/` Part 2 lab (Dockerfile, config generator, demo runner) | `tests/` | `benchmark_random.py` | `Dockerfile`
