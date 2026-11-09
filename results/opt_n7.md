# TDMA optimizer: 7 radios

## Your inputs

* Radio ranges (radio 0 = yours): 500, 300, 300, 200, 200, 100, 100 m
* Required coverage distance from your radio: 800 m
* Minimum spacing: 0.5 x the smaller range of the two radios
* Link length: 0.9 x the weaker radio's range
* Interference range: 1.5 x the transmitter's range
* Traffic: every radio sends 1 packet per frame to your radio (forwarding included), so a frame has at least 6 slots.

## Topologies that satisfy your rules (ranked by shortest TDMA frame (highest throughput), then lowest latency, then largest covered area)

| # | topology | arrangement | frame (slots) | reach (m) | hops | latency bound (slots) | covered area (km2) |
|---|---|---|---|---|---|---|---|
| 1 | custom (searched layout) | free-form search | 9 | 807 | 4 | 36 | 1.118 |
| 2 | chain (path graph) | random #8 | 12 | 810 | 4 | 48 | 1.119 |

Not possible: spider, 2 arms (reach 630 m < target 800 m); spider, 3 arms (reach 360 m < target 800 m); spider, 4 arms (reach 360 m < target 800 m); spider, 5 arms (reach 360 m < target 800 m); star (reach 270 m < target 800 m); binary tree (reach 532 m < target 800 m); ternary tree (reach 338 m < target 800 m); comb (reach 450 m < target 800 m); ring (cycle graph) (radios 1 and 2 only 90 m apart (rule needs >= 150 m))

## Best arrangement: **custom (searched layout)**

Farthest radio is 807 m from your radio over 4 hops; one TDMA frame is 9 slots (minimum possible 6); covered area 1.118 km2.

| radio | range (m) | x (m) | y (m) | sends to | distance to that radio (m) | hops | transmit slots |
|---|---|---|---|---|---|---|---|
| 0 (yours) | 500 | 0.0 | 0.0 | - | - | 0 | - |
| 1 | 300 | -456.1 | 665.5 | 2 | 269.2 | 4 | 0 |
| 2 | 300 | -289.8 | 453.8 | 4 | 179.8 | 3 | 7,8 |
| 3 | 200 | -96.6 | 150.9 | 0 | 179.2 | 1 | 0,1,2,3 |
| 4 | 200 | -194.0 | 301.6 | 3 | 179.5 | 2 | 4,5,6 |
| 5 | 100 | 49.9 | -35.0 | 0 | 61.0 | 1 | 4 |
| 6 | 100 | -29.1 | -77.3 | 0 | 82.6 | 1 | 5 |

Coordinates are in metres with your radio at (0, 0). Reception model: a link works up to the weaker radio's range scaled by the link length fraction; slot assignment is greedy.