# Evolution 3 on EMANE

Takes the optimizer's result (`results/opt_n*.json`) and runs its TDMA schedule on real EMANE radio models,
one network namespace per radio. It then sends one-way UDP from every radio at the same time and checks that each
radio's packets are heard by its parent.

* `gen_evo3.py`   result JSON -> EMANE configs, good and bad schedules, pathloss from each radio's range
* `udp_probe.py`  one-way broadcast probe (works for the receive-only gateway)
* `evo3_report.py` per-link delivery table
* `run_evo3.sh`   runs the lab: good, bad (two siblings share a slot, so a hidden-terminal collision), good again
* `Dockerfile`    Ubuntu 24.04 + EMANE 1.5.3 (same as Stage 1)

Expected: good and good_again deliver about 100% on every link; bad loses packets on the two colliding radios.
Multi-hop forwarding, adaptive rescheduling and relay-failure recovery are validated by `evo3_full.py` (see ../docs/EVO3_REPORT.md).
Not validated: timing drift, real radios, more than about 30 emulated radios on one laptop.
