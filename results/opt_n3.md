# TDMA optimizer: 3 radios

## Your inputs

* Number of radios: 3 (radio 0 = yours)
* Effective coverage: 100 m for every radio
* Needed distance from your radio: 5000 m

Model settings (change with flags): no two radios closer than 0.5 x the smaller range; links built at 0.9 x the weaker range; a transmitter blocks receivers within 1.5 x its range. Every radio sends 1 packet per frame to your radio (forwarding included), so a frame has at least 2 slots.

**5000 m cannot be reached with these 3 radios** (the best straight line reaches 180 m at this link length). Add radios, use longer coverage, or lower the distance. Showing the farthest layout instead.

## All feasible topologies, sorted best case first (farthest reach)

| # | topology | frame (slots) | reach (m) | hops | latency bound (slots) | covered area (km2) | area per slot (km2) |
|---|---|---|---|---|---|---|---|
| 1 | chain (path graph) | 3 | 180 | 2 | 6 | 0.067 | 0.0223 |
| 2 | star | 2 | 90 | 1 | 2 | 0.067 | 0.0334 |
| 3 | binary tree | 2 | 90 | 1 | 2 | 0.067 | 0.0334 |
| 4 | ternary tree | 2 | 90 | 1 | 2 | 0.066 | 0.0331 |

Best case for each goal:

* shortest frame (highest throughput): **star**
* lowest latency: **star**
* farthest reach: **chain (path graph)**
* largest covered area: **star**
* best balance (area per slot): **chain (path graph)**

## Chosen arrangement: **chain (path graph)**

Farthest radio is 180 m from your radio over 2 hops; one TDMA frame is 3 slots (minimum possible 2); covered area 0.067 km2.

| radio | range (m) | x (m) | y (m) | sends to | distance to that radio (m) | hops | transmit slots |
|---|---|---|---|---|---|---|---|
| 0 (yours) | 100 | 0.0 | 0.0 | - | - | 0 | - |
| 1 | 100 | 90.0 | 0.0 | 0 | 90.0 | 1 | 0,1 |
| 2 | 100 | 180.0 | 0.0 | 1 | 90.0 | 2 | 2 |

Coordinates are in metres with your radio at (0, 0); exact slot lists are in the CSV. Slot assignment is greedy.