# sim/

| File | Purpose |
|---|---|
| `vaanmegam_task_simulation.m` | MATLAB/Octave full simulation and report (colours the grid itself) |
| `tdma_sim.m` | MATLAB/Octave schedule comparison; `tdma_sim('Csv','schedule_sim.csv')` loads the Python Brain's schedule |
| `export_for_sims.py` | `schedule.json` -> `schedule_sim.csv` (name,x,y,slot) |
| `schedule_sim.csv` | Python Brain's schedule for the demo grid |
| `schedule_matlab.csv`, `schedule_matrix.txt`, `tdma_report.txt` | Output of the MATLAB full simulation |

MATLAB: `cd sim` then `tdma_sim('Csv','schedule_sim.csv')`. Results are written to `matlab_results.csv` and PNG figures in the current folder.
