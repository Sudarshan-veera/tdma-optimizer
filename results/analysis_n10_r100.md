# Topology analysis: 10 radios, range 100 m, 0 users

* Packets the user's gateway must receive per frame: **9** -> no topology can use a frame shorter than 9 slots (the gateway takes one packet per slot).

## Ranking (best balance first: metres of reach per frame slot)

| # | topology | frame (slots) | reach (m) | hops | latency bound (slots) | m per slot | Pareto-optimal |
|---|---|---|---|---|---|---|---|
| 1 | spider, 2 arms | 12 | 450 | 5 | 60 | 37.5 | yes |
| 2 | chain (path graph) | 24 | 810 | 9 | 216 | 33.8 | yes |
| 3 | spider, 3 arms | 9 | 270 | 3 | 27 | 30.0 | yes |
| 4 | spider, 4 arms | 9 | 270 | 3 | 27 | 30.0 | yes |
| 5 | ring (cycle graph) | 12 | 291 | 5 | 60 | 24.3 |  |
| 6 | comb | 20 | 450 | 5 | 100 | 22.5 |  |
| 7 | spider, 5 arms | 9 | 180 | 2 | 18 | 20.0 |  |
| 8 | spider, 6 arms | 9 | 180 | 2 | 18 | 20.0 |  |
| 9 | spider, 7 arms | 9 | 180 | 2 | 18 | 20.0 |  |
| 10 | spider, 8 arms | 9 | 180 | 2 | 18 | 20.0 |  |
| 11 | grid (2:1 rows:cols) | 20 | 371 | 5 | 100 | 18.6 |  |
| 12 | ladder (2 rows) | 20 | 371 | 5 | 100 | 18.6 |  |
| 13 | binary tree | 16 | 241 | 3 | 48 | 15.1 |  |
| 14 | 3 hubs + leaves | 11 | 147 | 2 | 22 | 13.4 |  |
| 15 | random geometric (best of 40) | 10 | 132 | 2 | 20 | 13.2 |  |
| 16 | random geometric (median) | 13 | 170 | 3 | 39 | 13.1 |  |
| 17 | ternary tree | 15 | 170 | 2 | 30 | 11.3 |  |
| 18 | star | 9 | 90 | 1 | 9 | 10.0 |  |

## Best case per goal

* **highest throughput (shortest frame):** star - frame 9 slots, reach 90 m, 1 hops
* **lowest latency (hops x frame):** star - frame 9 slots, reach 90 m, 1 hops
* **longest reach:** chain (path graph) - frame 24 slots, reach 810 m, 9 hops
* **best balance (metres of reach per slot):** spider, 2 arms - frame 12 slots, reach 450 m, 5 hops

## Why **spider, 2 arms** wins

* Its frame is **12** slots against a floor of 9: 3 extra slots are lost to conflicts between radios near the gateway.
* Conflict-graph colouring needs 3 slot groups for unit traffic; max radio degree 2, graph diameter 9 hops.
* It reaches 450 m (4.5 x Rc) over 5 hops; worst-case latency 60 slots.
* Among layouts at the frame floor, the longest reach is **spider, 3 arms** (270 m). Going further needs more slots: that is the reach-versus-throughput trade-off in the Pareto column.

## How the best case changes with the number of radios

| radios | shortest frame | longest reach | best balance |
|---|---|---|---|
| 5 | star (4 slots, 90 m) | chain (path graph) (9 slots, 360 m) | spider, 2 arms (4 slots, 180 m) |
| 8 | star (7 slots, 90 m) | chain (path graph) (18 slots, 630 m) | spider, 2 arms (9 slots, 360 m) |
| 10 | star (9 slots, 90 m) | chain (path graph) (24 slots, 810 m) | spider, 2 arms (12 slots, 450 m) |
| 15 | star (14 slots, 90 m) | chain (path graph) (39 slots, 1260 m) | spider, 2 arms (18 slots, 630 m) |
| 20 | star (19 slots, 90 m) | chain (path graph) (54 slots, 1710 m) | spider, 2 arms (27 slots, 900 m) |

Assumptions: disk interference model (interference range 1.5 x Rc), neighbouring radios 0.9 x Rc apart, convergecast traffic (every radio and user reports once per frame), greedy slot assignment (optimal on random trees, within 1 slot on grids; see results). Latency bound = hops x frame, conservative.