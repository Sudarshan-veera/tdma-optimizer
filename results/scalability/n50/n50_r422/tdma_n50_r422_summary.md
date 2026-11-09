```
TDMA topology analysis: 50 radios, range 422 m
rules: min spacing 0.5 x smaller range | link 0.9 x weaker range | interference 1.5 x own range | load 1 pkt/radio/frame
frame floor: gateway must receive 49 packets per frame -> no topology can use fewer slots
ranked by: best area per slot  (12 feasible topologies)

 # | topology        | frame | reach (m) | hops max/total | latency bound (slots) | area (km2) | km2/slot | best at                   
---+-----------------+-------+-----------+----------------+-----------------------+------------+----------+---------------------------
 1 | spider, 3 arms  |    49 |      6457 |         17/425 |              17 - 833 |      15.72 |   0.3209 | area per slot, frame, area
 2 | spider, 4 arms  |    49 |      4937 |         13/325 |              13 - 637 |      15.60 |   0.3183 |                           
 3 | spider, 5 arms  |    49 |      3798 |         10/265 |              10 - 490 |      15.41 |   0.3144 |                           
 4 | spider, 6 arms  |    49 |      3418 |          9/225 |               9 - 441 |      15.13 |   0.3087 |                           
 5 | spider, 8 arms  |    49 |      2659 |          7/175 |               7 - 343 |      14.19 |   0.2897 |                           
 6 | spider, 7 arms  |    51 |      2659 |          7/196 |               7 - 357 |      14.70 |   0.2882 |                           
 7 | spider, 9 arms  |    49 |      2279 |          6/159 |               6 - 294 |      13.58 |   0.2771 |                           
 8 | spider, 10 arms |    49 |      1899 |          5/145 |               5 - 245 |      12.83 |   0.2617 | latency                   
 9 | spider, 11 arms |    49 |      1899 |          5/135 |               5 - 245 |      12.03 |   0.2455 |                           
10 | spider, 2 arms  |    72 |      9495 |         25/625 |             25 - 1800 |      15.70 |   0.2181 |                           
11 | ring (cycle)    |    72 |      6049 |         25/625 |             25 - 1800 |      15.47 |   0.2149 |                           
12 | chain (path)    |   144 |     18610 |        49/1225 |             49 - 7056 |      15.70 |   0.1091 | reach                     

Rejected / infeasible:
  - spider, 12 arms: min-spacing violated (radios 11-12: 197 m < 211 m)
  - star: min-spacing violated (radios 19-20: 49 m < 211 m)
  - binary tree: all 8 layout variants fail, e.g. min-spacing violated (radios 18-19: 0 m < 211 m)
  - ternary tree: all 8 layout variants fail, e.g. min-spacing violated (radios 15-16: 0 m < 211 m)
  note: a complete tree needs sibling radios >= 2*asin(min_sep/(2*link_frac)) apart as seen from their parent;
        deep trees cannot be drawn in the plane under the spacing rule.

Best case per goal:
  * shortest frame                  : spider, 3 arms  (frame 49, reach 6457 m, 17 hops, latency 17-833 slots, area 15.72 km2, 0.3209 km2/slot)
  * lowest latency (hops x frame)   : spider, 10 arms  (frame 49, reach 1899 m, 5 hops, latency 5-245 slots, area 12.83 km2, 0.2617 km2/slot)
  * farthest reach                  : chain (path)  (frame 144, reach 18610 m, 49 hops, latency 49-7056 slots, area 15.70 km2, 0.1091 km2/slot)
  * largest covered area            : spider, 3 arms  (frame 49, reach 6457 m, 17 hops, latency 17-833 slots, area 15.72 km2, 0.3209 km2/slot)
  * best area per slot              : spider, 3 arms  (frame 49, reach 6457 m, 17 hops, latency 17-833 slots, area 15.72 km2, 0.3209 km2/slot)

Top-ranked: spider, 3 arms. Schedule-aware worst-case latency of the deepest radio (single packet, no queueing): 586 slots; frame overhead above the floor: 0 slots.
(elapsed 0.1 s)
```
