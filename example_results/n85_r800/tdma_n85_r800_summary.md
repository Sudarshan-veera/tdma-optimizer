```
TDMA topology analysis: 85 radios, range 800 m
rules: min spacing 0.5 x smaller range | link 0.9 x weaker range | interference 1.5 x own range | load 1 pkt/radio/frame
frame floor: gateway must receive 84 packets per frame -> no topology can use fewer slots
ranked by: best area per slot  (13 feasible topologies)

 # | topology                 | frame | reach (m) | hops max/total | latency bound (slots) | area (km2) | km2/slot | best at                   
---+--------------------------+-------+-----------+----------------+-----------------------+------------+----------+---------------------------
 1 | spider, 3 arms           |    84 |     20160 |        28/1218 |             28 - 2352 |      95.39 |   1.1356 | area per slot, frame, area
 2 | custom (searched layout) |    84 |     20160 |        28/1218 |             28 - 2352 |      95.39 |   1.1356 |                           
 3 | spider, 4 arms           |    84 |     15120 |         21/924 |             21 - 1764 |      94.93 |   1.1301 |                           
 4 | spider, 5 arms           |    84 |     12240 |         17/748 |             17 - 1428 |      94.30 |   1.1226 |                           
 5 | spider, 6 arms           |    84 |     10080 |         14/630 |             14 - 1176 |      93.21 |   1.1096 |                           
 6 | spider, 8 arms           |    84 |      7920 |         11/484 |              11 - 924 |      89.94 |   1.0707 |                           
 7 | spider, 9 arms           |    84 |      7200 |         10/435 |              10 - 840 |      87.71 |   1.0441 |                           
 8 | spider, 10 arms          |    84 |      6480 |          9/396 |               9 - 756 |      85.00 |   1.0119 |                           
 9 | spider, 7 arms           |    91 |      8640 |         12/546 |             12 - 1092 |      91.76 |   1.0083 |                           
10 | spider, 11 arms          |    84 |      5760 |          8/364 |               8 - 672 |      82.17 |   0.9782 | latency                   
11 | spider, 2 arms           |   123 |     30240 |        42/1806 |             42 - 5166 |      95.31 |   0.7749 |                           
12 | ring (cycle)             |   123 |     19482 |        42/1806 |             42 - 5166 |      94.49 |   0.7682 |                           
13 | chain (path)             |   249 |     60480 |        84/3570 |            84 - 20916 |      95.31 |   0.3828 | reach                     

Rejected / infeasible:
  - spider, 12 arms: min-spacing violated (radios 11-12: 373 m < 400 m)
  - star: min-spacing violated (radios 38-39: 54 m < 400 m)
  - binary tree: all 8 layout variants fail, e.g. min-spacing violated (radios 18-19: 0 m < 400 m)
  - ternary tree: all 8 layout variants fail, e.g. min-spacing violated (radios 15-16: 0 m < 400 m)
  note: a complete tree needs sibling radios >= 2*asin(min_sep/(2*link_frac)) apart as seen from their parent;
        deep trees cannot be drawn in the plane under the spacing rule.

Best case per goal:
  * shortest frame                  : spider, 3 arms  (frame 84, reach 20160 m, 28 hops, latency 28-2352 slots, area 95.39 km2, 1.1356 km2/slot)
  * lowest latency (hops x frame)   : spider, 11 arms  (frame 84, reach 5760 m, 8 hops, latency 8-672 slots, area 82.17 km2, 0.9782 km2/slot)
  * farthest reach                  : chain (path)  (frame 249, reach 60480 m, 84 hops, latency 84-20916 slots, area 95.31 km2, 0.3828 km2/slot)
  * largest covered area            : spider, 3 arms  (frame 84, reach 20160 m, 28 hops, latency 28-2352 slots, area 95.39 km2, 1.1356 km2/slot)
  * best area per slot              : spider, 3 arms  (frame 84, reach 20160 m, 28 hops, latency 28-2352 slots, area 95.39 km2, 1.1356 km2/slot)

Top-ranked: spider, 3 arms. Schedule-aware worst-case latency of the deepest radio (single packet, no queueing): 1596 slots; frame overhead above the floor: 0 slots.
Custom layout: annealed from 'spider, 3 arms', 2000 proposals -> no improvement over its starting layout.
(elapsed 4.5 s)
```
