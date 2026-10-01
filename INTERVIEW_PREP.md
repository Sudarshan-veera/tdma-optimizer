# Be able to answer these (in your own words)

1. **Why is distance-2 colouring the right model?** A receiver hears every transmitter in range.
   Two senders collide at a receiver B if both are B's neighbours (hidden terminal), and neighbours
   can't share a slot because they'd hear/jam each other. So conflicts = pairs within 2 hops = edges of G^2.
2. **Why DSATUR?** It colours the most constrained node first, so conflicts are discovered early;
   it is exact on bipartite graphs and typically within 1 colour of optimal on small graphs.
3. **Is the result optimal?** The max clique of G^2 is a lower bound. If we hit it, we are provably optimal.
   If not, the exact branch & bound (symmetry-broken, DSATUR-ordered) tries k-1 slots until it fails or times out.
4. **Complexity?** Colouring is NP-hard. Graph build is O(n^2), conflict graph O(n * deg^2), DSATUR O(n^2).
   Exact search is exponential worst-case, hence the time limit.
5. **How do you know it's collision-free?** The verifier uses raw geometry and a different code path
   (neighbour lists and neighbour pairs) from the Brain. 76 tests incl. 60 random topologies.
6. **Edge cases?** Isolated nodes share slot 0; fully connected N nodes need N slots; range boundary
   is inclusive (<= 500 m); bad JSON/NaN gives exit code 2.
7. **Limitations?** Assumes a binary disk model (real RF has SINR/fading), static nodes, one frequency,
   one transmit slot per node per frame (no traffic-aware or per-link scheduling, no multi-frequency reuse).
8. **Improvements?** Link scheduling (edge colouring) for unicast, weighting slots by traffic demand,
   multiple frequencies (EMANE supports per-slot frequency), incremental recolouring when nodes move.
9. **Link to your LoRa token-passing project:** token passing = 1 transmitter per window = N slots.
   This project is the generalisation that lets distant nodes transmit simultaneously (9 vs 16 slots here).
10. **How does the bridge enforce the schedule?** One `<slot index=s nodes=...><tx/></slot>` per slot,
    unlisted slots default to receive; the pathloss EEL makes out-of-range nodes unreachable.
