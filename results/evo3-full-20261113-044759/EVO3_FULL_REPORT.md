# Evolution 3 full run: 12 radios, frame 11 (custom (searched layout))

Mode: **emane**

## distributed_scheduling

Status: computed_local_negotiation (not over real radio messages)

```json
{
 "radios": 11,
 "conflict_violations": 0,
 "frame_distributed": 13,
 "frame_centralized_best": 11,
 "frame_overhead_pct": 18.2,
 "transmissions": 18
}
```

## fading_sinr

Status: simulated (Monte Carlo, not EMANE; EMANE here uses binary 80/200 dB pathloss, so it cannot show SINR effects)

```json
{
 "frames": 500,
 "pdr": {
  "optimizer_schedule": {
   "none+0dB": 1.0,
   "rayleigh+0dB": 0.5121,
   "rayleigh+3dB": 0.6698,
   "rayleigh+6dB": 0.7639,
   "rayleigh+10dB": 0.8294,
   "rayleigh+15dB": 0.857,
   "rician+0dB": 0.6316,
   "rician+3dB": 0.8111,
   "rician+6dB": 0.8792,
   "rician+10dB": 0.9113,
   "rician+15dB": 0.9221
  },
  "sinr_safe_schedule": {
   "none+0dB": 1.0,
   "rayleigh+0dB": 0.5121,
   "rayleigh+3dB": 0.6698,
   "rayleigh+6dB": 0.7639,
   "rayleigh+10dB": 0.8294,
   "rayleigh+15dB": 0.857,
   "rician+0dB": 0.6316,
   "rician+3dB": 0.8111,
   "rician+6dB": 0.8792,
   "rician+10dB": 0.9113,
   "rician+15dB": 0.9221
  }
 },
 "frame_optimizer": 11,
 "frame_sinr_safe": 11,
 "sinr_safe_frame_overhead_pct": 0.0,
 "note": "no-fading rows show whether the schedule is SINR-safe at all; boost columns = extra transmit power as fade margin"
}
```

## energy_aware

Status: modelled (assumed power values, no hardware measurement)

```json
{
 "power_w": {
  "tx": 1.2,
  "rx": 0.9,
  "idle": 0.25,
  "sleep": 0.03
 },
 "baseline_j_per_frame": 0.1242,
 "aware_j_per_frame": 0.04068,
 "saving_pct": 67.25,
 "policy": "a radio listens only in slots where one of its own children transmits, sleeps otherwise"
}
```

## clock_sync

Status: simulated (assumed drift, no hardware clocks)

```json
{
 "radios": 11,
 "assumed_max_drift_ppm": 20.0,
 "beacon_interval_s": 1.0,
 "initial_max_offset_us": 397.4,
 "unsynchronised_offset_after_sim_us": 1061.5,
 "worst_offset_before_a_beacon_us": 408.4,
 "offset_after_sync_us": 1.51,
 "recommended_guard_us": 32,
 "slot_us": 10000,
 "guard_fraction_of_slot": 0.0032,
 "guard_fits_in_slot": true
}
```

## self_healing_algorithm

Status: computed (algorithm level; the live test is reported separately)

```json
{
 "relay_failures_tested": 3,
 "recoverable": 0
}
```

## multi_hop

Status: measured_emane

```json
{
 "routes": {
  "2": [
   2,
   1
  ],
  "3": [
   3,
   1
  ],
  "4": [
   4,
   6,
   5,
   2,
   1
  ],
  "5": [
   5,
   2,
   1
  ],
  "6": [
   6,
   5,
   2,
   1
  ],
  "7": [
   7,
   1
  ],
  "8": [
   8,
   1
  ],
  "9": [
   9,
   1
  ],
  "10": [
   10,
   2,
   1
  ],
  "11": [
   11,
   1
  ],
  "12": [
   12,
   1
  ]
 },
 "windows": [
  {
   "pdr_pct": 100.0,
   "sent": 976,
   "received": 976
  },
  {
   "pdr_pct": 100.0,
   "sent": 976,
   "received": 976
  },
  {
   "pdr_pct": 100.0,
   "sent": 976,
   "received": 976
  },
  {
   "pdr_pct": 100.0,
   "sent": 976,
   "received": 976
  }
 ],
 "pdr_pct_mean_sd": [
  100.0,
  0.0
 ],
 "latency_ms_by_path_length": {
  "1": 50.6,
  "2": 107.1,
  "3": 204.6,
  "4": 298.9
 }
}
```

## predictive

Status: measured_emane (walk-forward: forecast window k from windows < k)

```json
{
 "windows": 4,
 "forecasts_scored": 22,
 "pdr_forecast_mae": 0.0,
 "persistence_baseline_mae": 0.0,
 "note": "with near-100% PDR both errors are tiny; the forecast is only useful when links degrade"
}
```

## adaptive_scheduling

Status: measured_emane

```json
{
 "surge_node": 3,
 "surge_x_of_own_slot_capacity": 2.0,
 "assumed_packets_per_slot": 29,
 "surge_pps": 527.3,
 "planned_utilisation": 0.8,
 "slots_before": 1,
 "slots_after": 3,
 "frame_before": 11,
 "frame_after": 11,
 "frame_best_case_scheduler_same_demand": 9,
 "changed_radios": [
  2,
  3,
  5,
  6
 ],
 "conflict_violations": 0,
 "surge_node_pdr_pct": {
  "static": 75.85,
  "adaptive": 100.0
 },
 "network_pdr_pct": {
  "static": 78.92,
  "adaptive": 100.0
 }
}
```

## self_healing_live

Status: measured_emane

```json
{
 "failed_relay": 5,
 "affected_nodes": [
  4,
  6
 ],
 "detected_from_delivery": true,
 "new_parents": {
  "6": 2
 },
 "frame_before": 13,
 "frame_after": 10,
 "pdr_pct_of_surviving_nodes": {
  "before_failure": 100.0,
  "during_failure": 79.28,
  "after_recovery": 99.76
 },
 "relay_failures_tested": 3,
 "recoverable_at_design_coverage": 0,
 "coverage_multiplier_needed_per_relay": {
  "5": 1.75,
  "6": 1.75
 },
 "relays_never_recoverable_within_3x": [
  2
 ],
 "coverage_multiplier_used": 1.75,
 "note": "the failure is a stopped relay process; detection uses one measurement window, so recovery time is about one window plus schedule publication"
}
```
