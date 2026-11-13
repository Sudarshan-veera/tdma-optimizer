# Repeat runs (12 radios, EMANE)

4 complete runs: evo3-full-20261111-082053, evo3-full-20261113-044759, evo3-full-20261113-045325, evo3-full-20261113-045848

| Experiment | Mean | Min | Max |
|---|---|---|---|
| Multi-hop delivery (%) | 99.98 | 99.92 | 100.00 |
| Optimized schedule, before collision (%) | 99.65 | 99.35 | 99.84 |
| Forced slot collision (%) | 92.94 | 90.05 | 94.29 |
| Optimized schedule restored (%) | 99.78 | 99.67 | 99.84 |
| Surged radio, static (%) | 75.81 | 75.71 | 75.94 |
| Surged radio, adaptive (%) | 100.00 | 100.00 | 100.00 |
| Relay failed, before (%) | 99.97 | 99.86 | 100.00 |
| Relay failed, during (%) | 79.82 | 79.28 | 80.00 |
| Relay failed, after recovery (%) | 99.94 | 99.76 | 100.00 |

Each row is computed from the run folders listed above; the same numbers are in each run's `evo3_full_report.json`.
