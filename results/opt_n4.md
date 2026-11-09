# TDMA optimizer: 4 radios

## Your inputs

* Number of radios: 4 (radio 0 = yours)
* Effective coverage: 45, 450, 300, 500 m
* Needed distance from your radio: not set (all arrangements are compared)

Model settings (change with flags): no two radios closer than 0.5 x the smaller range; links built at 0.9 x the weaker range; a transmitter blocks receivers within 1.5 x its range. Every radio sends 1 packet per frame to your radio (forwarding included), so a frame has at least 3 slots.

## All feasible topologies, sorted best case first (most covered area per TDMA slot)

| # | topology | frame (slots) | reach (m) | hops | latency bound (slots) | covered area (km2) | area per slot (km2) |
|---|---|---|---|---|---|---|---|
| 1 | custom (searched layout) | 5 | 424 | 2 | 10 | 1.140 | 0.2280 |
| 2 | chain (path graph) | 6 | 580 | 3 | 18 | 1.198 | 0.1996 |

Not possible with these radios and rules: spider, 2 arms (radios 1 and 3 only 81 m apart (rule needs >= 225 m)); star (radios 1 and 3 only 70 m apart (rule needs >= 225 m)); binary tree (radios 1 and 3 only 81 m apart (rule needs >= 225 m)); ternary tree (radios 1 and 3 only 70 m apart (rule needs >= 225 m)); comb (radios 1 and 3 only 57 m apart (rule needs >= 225 m)); ring (cycle graph) (radios 1 and 3 only 41 m apart (rule needs >= 225 m))

Best case for each goal:

* shortest frame (highest throughput): **custom (searched layout)**
* lowest latency: **custom (searched layout)**
* farthest reach: **chain (path graph)**
* largest covered area: **chain (path graph)**
* best balance (area per slot): **custom (searched layout)**

## Chosen arrangement: **custom (searched layout)**

Farthest radio is 424 m from your radio over 2 hops; one TDMA frame is 5 slots (minimum possible 3); covered area 1.140 km2.

| radio | range (m) | x (m) | y (m) | sends to | distance to that radio (m) | hops | transmit slots |
|---|---|---|---|---|---|---|---|
| 0 (yours) | 45 | 0.0 | 0.0 | - | - | 0 | - |
| 1 | 450 | 0.5 | -39.9 | 0 | 39.9 | 1 | 0,1,2 |
| 2 | 300 | -238.3 | 79.5 | 1 | 267.0 | 2 | 3 |
| 3 | 500 | 365.0 | -215.0 | 1 | 404.3 | 2 | 4 |

Coordinates are in metres with your radio at (0, 0); exact slot lists are in the CSV. Slot assignment is greedy.