# TDMA optimizer: 5 radios

## Your inputs

* Number of radios: 5 (radio 0 = yours)
* Effective coverage: 500, 300, 300, 200, 100 m
* Needed distance from your radio: 600 m

Model settings (change with flags): no two radios closer than 0.5 x the smaller range; links built at 0.9 x the weaker range; a transmitter blocks receivers within 1.5 x its range. Every radio sends 1 packet per frame to your radio (forwarding included), so a frame has at least 4 slots.

## All feasible topologies, sorted best case first (most covered area per TDMA slot)

| # | topology | frame (slots) | reach (m) | hops | latency bound (slots) | covered area (km2) | area per slot (km2) |
|---|---|---|---|---|---|---|---|
| 1 | chain (path graph) | 6 | 630 | 3 | 18 | 1.018 | 0.1697 |
| 2 | custom (searched layout) | 6 | 630 | 3 | 18 | 1.018 | 0.1697 |

Not possible with these radios and rules: spider, 2 arms (reach 450 m < target 600 m); spider, 3 arms (reach 450 m < target 600 m); star (reach 270 m < target 600 m); binary tree (reach 532 m < target 600 m); ternary tree (reach 507 m < target 600 m); comb (reach 360 m < target 600 m); ring (cycle graph) (radios 0 and 1 only 90 m apart (rule needs >= 150 m))

Best case for each goal:

* shortest frame (highest throughput): **chain (path graph)**
* lowest latency: **chain (path graph)**
* farthest reach: **chain (path graph)**
* largest covered area: **chain (path graph)**
* best balance (area per slot): **chain (path graph)**

## Chosen arrangement: **chain (path graph)**

Farthest radio is 630 m from your radio over 3 hops; one TDMA frame is 6 slots (minimum possible 4); covered area 1.018 km2.

| radio | range (m) | x (m) | y (m) | sends to | distance to that radio (m) | hops | transmit slots |
|---|---|---|---|---|---|---|---|
| 0 (yours) | 500 | 0.0 | 0.0 | - | - | 0 | - |
| 1 | 300 | 630.0 | 0.0 | 2 | 270.0 | 3 | 5 |
| 2 | 300 | 360.0 | 0.0 | 3 | 180.0 | 2 | 3,4 |
| 3 | 200 | 180.0 | 0.0 | 0 | 180.0 | 1 | 0,1,2 |
| 4 | 100 | 90.0 | 0.0 | 0 | 90.0 | 1 | 5 |

Coordinates are in metres with your radio at (0, 0); exact slot lists are in the CSV. Slot assignment is greedy.