# TDMA Evolution Add-on

This additive patch introduces reusable implementations for the eight requested advancement areas without overwriting existing project files.

- `LiveAdaptiveRuntime`: repeated queue/PDR/link-quality sampling, queue-demand prediction, existing `AdaptiveTDMA` adaptation, churn limit and schedule publisher callback. `emane/live_adaptive.py` connects this loop to the project schedule XML helpers and can optionally publish with `emaneevent-tdmaschedule`.
- `MultiHopRouting` and `SelfHealingManager`: multi-hop route cost based on ETX/PDR, alternate-parent selection and immediate child recovery.
- `FadingSINRModel`: Rayleigh/Rician fading power gain and SINR threshold checks.
- `OnlineMetricPredictor`: online linear-trend prediction for queue depth and PDR; predictions can feed the existing adaptive controller.
- `DistributedSlotAgent`: local-neighbour reservation exchange without a central scheduler.
- `EnergyModel`: TX/RX/idle/sleep energy accounting per frame.
- `ClockModel`: drift tracking, resynchronization and guard-interval calculation.
- `emane/multihop_probe.py`: UDP send/relay/sink utility with end-to-end sequence, path and latency reporting.

The UDP relay must be launched in each intermediate NEM namespace using that NEM's parent from the current plan. The live controller reads a JSON metrics snapshot supplied by a collector; the JSON format is shown in `METRICS_FORMAT.json`. It does not scrape EMANE queue counters itself because the exact `emanesh` statistic names depend on the configured EMANE model.

Run tests from the project root:

```bash
.venv/bin/python -m pytest -q
```
