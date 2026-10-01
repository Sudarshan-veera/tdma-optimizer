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
`emane_bridge.py schedule.json` writes
* `schedule.xml`: EMANE TDMA full schedule (1 frame, 1000 us slots, `nodes='1,4,13,16'` = spatial reuse),
* `scenario.eel`: pathloss events (80 dB in range, 200 dB out of range) so EMANE matches the 500 m model.

Apply with `emaneevent-tdmaschedule schedule.xml -i lo`, check acceptance with
`emanesh localhost get stat 1 mac | grep scheduler`.

**Status:** (fill in honestly after you try it: what you installed, what ran, what you observed.)

## Layout
`tdma_brain.py` Brain/CLI | `emane_bridge.py` EMANE glue | `tests/` | `benchmark_random.py` | `Dockerfile`
