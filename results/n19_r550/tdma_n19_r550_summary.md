```
TDMA topology analysis: 19 radios, range 550 m
rules: min spacing 0.5 x smaller range | link 0.9 x weaker range | interference 1.5 x own range | load 1 pkt/radio/frame
frame floor: gateway must receive 18 packets per frame -> no topology can use fewer slots
ranked by: best area per slot  (15 feasible topologies)

 # | topology                 | frame | reach (m) | hops max/total | latency bound (slots) | area (km2) | km2/slot | best at            
---+--------------------------+-------+-----------+----------------+-----------------------+------------+----------+--------------------
 1 | spider, 3 arms           |    18 |      2970 |           6/63 |               6 - 108 |      10.40 |   0.5778 | area per slot, area
 2 | custom (searched layout) |    18 |      3155 |           7/66 |               7 - 126 |      10.38 |   0.5765 | frame              
 3 | spider, 4 arms           |    18 |      2475 |           5/50 |                5 - 90 |      10.22 |   0.5677 |                    
 4 | spider, 5 arms           |    18 |      1980 |           4/42 |                4 - 72 |       9.88 |   0.5491 |                    
 5 | spider, 6 arms           |    18 |      1485 |           3/36 |                3 - 54 |       9.39 |   0.5218 |                    
 6 | spider, 7 arms           |    18 |      1485 |           3/33 |                3 - 54 |       8.66 |   0.4814 |                    
 7 | spider, 8 arms           |    18 |      1485 |           3/30 |                3 - 54 |       7.82 |   0.4346 |                    
 8 | spider, 2 arms           |    24 |      4455 |           9/90 |               9 - 216 |      10.40 |   0.4334 |                    
 9 | ring (cycle)             |    24 |      2997 |           9/90 |               9 - 216 |       9.98 |   0.4160 |                    
10 | binary tree              |    24 |      1629 |           4/50 |                4 - 96 |       9.53 |   0.3971 |                    
11 | spider, 9 arms           |    18 |       990 |           2/27 |                2 - 36 |       6.91 |   0.3841 |                    
12 | spider, 10 arms          |    18 |       990 |           2/26 |                2 - 36 |       6.40 |   0.3556 | latency            
13 | ternary tree             |    23 |      1354 |           3/39 |                3 - 69 |       7.56 |   0.3287 |                    
14 | spider, 11 arms          |    18 |       990 |           2/25 |                2 - 36 |       5.87 |   0.3263 |                    
15 | chain (path)             |    51 |      8910 |         18/171 |              18 - 918 |      10.40 |   0.2039 | reach              

Rejected / infeasible:
  - spider, 12 arms: min-spacing violated (radios 11-12: 256 m < 275 m)
  - star: min-spacing violated (radios 14-15: 172 m < 275 m)

Best case per goal:
  * shortest frame                  : custom (searched layout)  (frame 18, reach 3155 m, 7 hops, latency 7-126 slots, area 10.38 km2, 0.5765 km2/slot)
  * lowest latency (hops x frame)   : spider, 10 arms  (frame 18, reach 990 m, 2 hops, latency 2-36 slots, area 6.40 km2, 0.3556 km2/slot)
  * farthest reach                  : chain (path)  (frame 51, reach 8910 m, 18 hops, latency 18-918 slots, area 10.40 km2, 0.2039 km2/slot)
  * largest covered area            : spider, 3 arms  (frame 18, reach 2970 m, 6 hops, latency 6-108 slots, area 10.40 km2, 0.5778 km2/slot)
  * best area per slot              : spider, 3 arms  (frame 18, reach 2970 m, 6 hops, latency 6-108 slots, area 10.40 km2, 0.5778 km2/slot)

Top-ranked: spider, 3 arms. Schedule-aware worst-case latency of the deepest radio (single packet, no queueing): 82 slots; frame overhead above the floor: 0 slots.
Custom layout: annealed from 'spider, 3 arms', 2000 proposals -> no improvement over its starting layout.
(elapsed 3.2 s)
```
