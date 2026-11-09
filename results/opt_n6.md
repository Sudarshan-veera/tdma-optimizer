# TDMA optimizer: 6 radios

## Your inputs

* Radio ranges (radio 0 = yours): 500, 300, 300, 200, 100, 100 m
* Required coverage distance from your radio: 700 m
* Minimum spacing: 0.5 x the smaller range of the two radios
* Link length: 0.9 x the weaker radio's range
* Interference range: 1.5 x the transmitter's range
* Traffic: every radio sends 1 packet per frame to your radio (forwarding included), so a frame has at least 5 slots.

## Topologies that satisfy your rules (ranked by shortest TDMA frame (highest throughput), then lowest latency, then largest covered area)

| # | topology | arrangement | frame (slots) | reach (m) | hops | latency bound (slots) | covered area (km2) |
|---|---|---|---|---|---|---|---|
| 1 | spider, 2 arms | alternating | 6 | 720 | 3 | 18 | 0.988 |
| 2 | custom (searched layout) | free-form search | 6 | 720 | 3 | 18 | 0.988 |
| 3 | chain (path graph) | random #7 | 7 | 720 | 3 | 21 | 0.988 |

Not possible: spider, 3 arms (reach 450 m < target 700 m); spider, 4 arms (reach 450 m < target 700 m); star (reach 270 m < target 700 m); binary tree (reach 356 m < target 700 m); ternary tree (reach 360 m < target 700 m); comb (reach 270 m < target 700 m); ring (cycle graph) (radios 0 and 1 only 90 m apart (rule needs >= 150 m))

## Best arrangement: **spider, 2 arms**

Farthest radio is 720 m from your radio over 3 hops; one TDMA frame is 6 slots (minimum possible 5); covered area 0.988 km2.

| radio | range (m) | x (m) | y (m) | sends to | distance to that radio (m) | hops | transmit slots |
|---|---|---|---|---|---|---|---|
| 0 (yours) | 500 | 0.0 | 0.0 | - | - | 0 | - |
| 1 | 300 | 270.0 | 0.0 | 0 | 270.0 | 1 | 0,1,2 |
| 2 | 300 | 540.0 | 0.0 | 1 | 270.0 | 2 | 3,4 |
| 3 | 200 | 720.0 | 0.0 | 2 | 180.0 | 3 | 5 |
| 4 | 100 | -180.0 | 0.0 | 5 | 90.0 | 2 | 5 |
| 5 | 100 | -90.0 | 0.0 | 0 | 90.0 | 1 | 3,4 |

Coordinates are in metres with your radio at (0, 0). Reception model: a link works up to the weaker radio's range scaled by the link length fraction; slot assignment is greedy.