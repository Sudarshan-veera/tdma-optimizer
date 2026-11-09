# TDMA optimizer: 12 radios, ranges 500, 400, 300, 300, 200, 200, 150, 100, 100, 80, 80, 60 m

* Goal: **most covered area per slot**. Rule: radios at least 0.50 x the smaller range apart; links built at 0.90 x the weaker radio's range.
* The user's radio (radio 0, range 500 m) must receive 11 packets per frame, so every frame is at least 11 slots.

## Ranking of topologies (best arrangement of each)

| # | topology | arrangement | frame (slots) | covered area (km2) | reach (m) | hops | latency bound (slots) |
|---|---|---|---|---|---|---|---|
| 1 | custom (searched layout) | free-form search | 11 | 1.217 | 865 | 4 | 44 |
| 2 | spider, 8 arms | random #25 | 11 | 1.068 | 630 | 2 | 22 |
| 3 | spider, 5 arms | random #14 | 12 | 1.164 | 594 | 3 | 36 |
| 4 | spider, 3 arms | largest ranges near the user | 11 | 1.047 | 702 | 4 | 44 |
| 5 | spider, 6 arms | random #10 | 11 | 1.045 | 450 | 2 | 22 |
| 6 | star | random #6 | 11 | 1.020 | 360 | 1 | 11 |
| 7 | ternary tree | largest ranges near the user | 11 | 1.020 | 540 | 2 | 22 |
| 8 | spider, 4 arms | random #13 | 12 | 1.066 | 630 | 2 | 24 |
| 9 | spider, 2 arms | random #23 | 14 | 1.204 | 792 | 4 | 56 |
| 10 | binary tree | random #8 | 14 | 1.171 | 694 | 3 | 42 |
| 11 | comb | random #17 | 16 | 1.130 | 702 | 4 | 64 |
| 12 | chain (path graph) | smallest ranges near the user | 30 | 1.587 | 1467 | 11 | 330 |

Not feasible: ring (cycle graph) (radios 0 and 1 only 54 m apart (rule needs >= 200 m))

## Best: **custom (searched layout)**, free-form search

Covered area 1.217 km2, farthest radio 865 m from the user over 4 hops, frame 11 slots (floor 11).

| radio | range (m) | x (m) | y (m) | sends to | link length (m) | hops | slots |
|---|---|---|---|---|---|---|---|
| 0 (user) | 500 | 0.0 | 0.0 | - | - | 0 | - |
| 1 | 400 | 229.5 | 274.4 | 0 | 357.7 | 1 | 0,1,2,3,4 |
| 2 | 300 | -191.0 | 189.3 | 0 | 268.9 | 1 | 8 |
| 3 | 300 | 674.9 | 541.2 | 5 | 178.9 | 4 | 10 |
| 4 | 200 | 375.7 | 375.6 | 1 | 177.9 | 2 | 5,6,7 |
| 5 | 200 | 516.4 | 458.4 | 4 | 163.3 | 3 | 8,9 |
| 6 | 150 | 100.3 | 90.3 | 0 | 135.0 | 1 | 9 |
| 7 | 100 | 62.4 | 2.9 | 0 | 62.5 | 1 | 5 |
| 8 | 100 | -21.5 | 70.9 | 0 | 74.0 | 1 | 6 |
| 9 | 80 | 280.4 | 262.4 | 1 | 52.3 | 2 | 10 |
| 10 | 80 | -59.1 | -23.0 | 0 | 63.4 | 1 | 7 |
| 11 | 60 | 18.0 | -46.1 | 0 | 49.5 | 1 | 10 |

Model: disk reception per radio (link works up to the weaker end's range), a transmitter jams receivers within 1.5 x its own range, convergecast traffic, greedy slot assignment. Link length 0.9 x range leaves a 10% fade margin.