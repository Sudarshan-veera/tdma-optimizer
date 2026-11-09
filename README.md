# TDMA topology optimizer

    pip install numpy matplotlib
    python3 tdma_topology_optimizer.py

The script pauses and asks:

    Enter the total number of radios to configure:
    Enter the effective coverage radius of each radio (in meters):

Nothing about n or r is hardcoded. Model: min spacing 0.5x smaller range, link 0.9x weaker range,
interference 1.5x own range, 1 packet per radio per frame to the gateway (radio 0).
Results are written to `results/n<N>_r<R>/` (ranked summary, best layout PNG, coordinates CSV/JSON,
comparison figure). Optional flags: `--help`. `example_results/` holds a run for n=85, r=800.
