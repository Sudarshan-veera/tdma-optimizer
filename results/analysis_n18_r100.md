# Topology analysis: 18 radios, range 100 m, 40 users, target 800 m

* Packets the user's gateway must receive per frame: **57** -> no topology can use a frame shorter than 57 slots (the gateway takes one packet per slot).

## Ranking (only topologies reaching >= 800 m, shortest frame first)

| # | topology | frame (slots) | reach (m) | hops | latency bound (slots) | m per slot | Pareto-optimal |
|---|---|---|---|---|---|---|---|
| 1 | spider, 2 arms | 89 | 810 | 9 | 801 | 9.1 | yes |
| 2 | search-optimised layout | 89 | 810 | 9 | 801 | 9.1 | yes |
| 3 | comb | 146 | 810 | 9 | 1314 | 5.5 |  |
| 4 | chain (path graph) | 158 | 1530 | 17 | 2686 | 9.7 | yes |

Excluded (reach below the target): star (90 m), grid (2:1 rows:cols) (485 m), ring (cycle graph) (518 m), binary tree (319 m), 3 hubs + leaves (170 m), spider, 3 arms (540 m), spider, 4 arms (450 m), spider, 5 arms (360 m), spider, 6 arms (270 m), spider, 7 arms (270 m), spider, 8 arms (270 m), ternary tree (255 m), ladder (2 rows) (726 m), random geometric (median) (192 m), random geometric (best of 40) (169 m)

## Best case per goal

* **highest throughput (shortest frame):** spider, 2 arms - frame 89 slots, reach 810 m, 9 hops
* **lowest latency (hops x frame):** spider, 2 arms - frame 89 slots, reach 810 m, 9 hops
* **longest reach:** chain (path graph) - frame 158 slots, reach 1530 m, 17 hops
* **best balance (metres of reach per slot):** chain (path graph) - frame 158 slots, reach 1530 m, 17 hops

## Why **spider, 2 arms** wins

* Its frame is **89** slots against a floor of 57: 32 extra slots are lost to conflicts between radios near the gateway.
* Conflict-graph colouring needs 3 slot groups for unit traffic; max radio degree 2, graph diameter 17 hops.
* It reaches 810 m (8.1 x Rc) over 9 hops; worst-case latency 801 slots.
* Among layouts at the frame floor, the longest reach is **spider, 3 arms** (540 m). Going further needs more slots: that is the reach-versus-throughput trade-off in the Pareto column.

## How the best case changes with the number of radios

| radios | shortest frame | longest reach | best balance |
|---|---|---|---|
| 9 | star (48 slots, 90 m) | chain (path graph) (122 slots, 720 m) | spider, 2 arms (53 slots, 360 m) |
| 14 | star (53 slots, 90 m) | chain (path graph) (143 slots, 1170 m) | spider, 3 arms (53 slots, 450 m) |
| 18 | star (57 slots, 90 m) | chain (path graph) (158 slots, 1530 m) | chain (path graph) (158 slots, 1530 m) |
| 27 | star (66 slots, 90 m) | chain (path graph) (187 slots, 2340 m) | chain (path graph) (187 slots, 2340 m) |
| 36 | star (75 slots, 90 m) | chain (path graph) (217 slots, 3150 m) | chain (path graph) (217 slots, 3150 m) |

Assumptions: disk interference model (interference range 1.5 x Rc), neighbouring radios 0.9 x Rc apart, convergecast traffic (every radio and user reports once per frame), greedy slot assignment (optimal on random trees, within 1 slot on grids; see results). Latency bound = hops x frame, conservative.