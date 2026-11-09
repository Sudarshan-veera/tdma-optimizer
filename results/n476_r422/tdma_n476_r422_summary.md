```
TDMA topology analysis: 476 radios, range 422 m
rules: min spacing 0.5 x smaller range | link 0.9 x weaker range | interference 1.5 x own range | load 1 pkt/radio/frame
frame floor: gateway must receive 475 packets per frame -> no topology can use fewer slots
ranked by: best area per slot  (13 feasible topologies)

 # | topology                 | frame | reach (m) | hops max/total | latency bound (slots) | area (km2) | km2/slot | best at      
---+--------------------------+-------+-----------+----------------+-----------------------+------------+----------+--------------
 1 | spider, 4 arms           |   475 |     45196 |      119/28441 |           119 - 56525 |     147.30 |   0.3101 | area per slot
 2 | spider, 5 arms           |   475 |     36081 |       95/22800 |            95 - 45125 |     147.21 |   0.3099 |              
 3 | spider, 3 arms           |   475 |     60388 |      159/37842 |           159 - 75525 |     147.05 |   0.3096 | frame        
 4 | spider, 6 arms           |   475 |     30384 |       80/19040 |            80 - 38000 |     146.93 |   0.3093 |              
 5 | spider, 8 arms           |   475 |     22788 |       60/14340 |            60 - 28500 |     146.39 |   0.3082 |              
 6 | spider, 9 arms           |   475 |     20129 |       53/12773 |            53 - 25175 |     145.40 |   0.3061 |              
 7 | spider, 10 arms          |   475 |     18230 |       48/11520 |            48 - 22800 |     144.71 |   0.3046 |              
 8 | spider, 11 arms          |   475 |     16711 |       44/10494 |            44 - 20900 |     143.79 |   0.3027 | latency      
 9 | custom (searched layout) |   495 |     45196 |      119/26347 |           119 - 58905 |     146.29 |   0.2955 |              
10 | spider, 7 arms           |   537 |     25826 |       68/16354 |            68 - 36516 |     146.41 |   0.2726 |              
11 | spider, 2 arms           |   711 |     90392 |      238/56644 |          238 - 169218 |     147.37 |   0.2073 | area         
12 | ring (cycle)             |   711 |     57546 |      238/56644 |          238 - 169218 |     147.20 |   0.2070 |              
13 | chain (path)             |  1422 |    180405 |     475/113050 |          475 - 675450 |     147.37 |   0.1036 | reach        

Rejected / infeasible:
  - spider, 12 arms: min-spacing violated (radios 11-12: 197 m < 211 m)
  - star: min-spacing violated (radios 408-409: 5 m < 211 m)
  - binary tree: all 8 layout variants fail, e.g. min-spacing violated (radios 18-19: 0 m < 211 m)
  - ternary tree: all 8 layout variants fail, e.g. min-spacing violated (radios 15-16: 0 m < 211 m)
  note: a complete tree needs sibling radios >= 2*asin(min_sep/(2*link_frac)) apart as seen from their parent;
        deep trees cannot be drawn in the plane under the spacing rule.

Best case per goal:
  * shortest frame                  : spider, 3 arms  (frame 475, reach 60388 m, 159 hops, latency 159-75525 slots, area 147.05 km2, 0.3096 km2/slot)
  * lowest latency (hops x frame)   : spider, 11 arms  (frame 475, reach 16711 m, 44 hops, latency 44-20900 slots, area 143.79 km2, 0.3027 km2/slot)
  * farthest reach                  : chain (path)  (frame 1422, reach 180405 m, 475 hops, latency 475-675450 slots, area 147.37 km2, 0.1036 km2/slot)
  * largest covered area            : spider, 2 arms  (frame 711, reach 90392 m, 238 hops, latency 238-169218 slots, area 147.37 km2, 0.2073 km2/slot)
  * best area per slot              : spider, 4 arms  (frame 475, reach 45196 m, 119 hops, latency 119-56525 slots, area 147.30 km2, 0.3101 km2/slot)

Top-ranked: spider, 4 arms. Schedule-aware worst-case latency of the deepest radio (single packet, no queueing): 28498 slots; frame overhead above the floor: 0 slots.
Custom layout: annealed from 'spider, 4 arms', 2000 proposals -> no improvement over its starting layout.
(elapsed 104.7 s)
```
