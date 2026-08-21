# Task: shrink the die

## Design
- Platform: `nangate45`
- Design: `gcd`
- Flow: OpenROAD-flow-scripts (RTL to GDS)

## Goal
This design already builds correctly and meets timing. It is also **larger than
it needs to be**. Make the die smaller by tuning flow knobs.

You must reduce `finish__design__die__area` by at least **2.0%** relative
to the default configuration, **without** regressing correctness.

## What you may change
Only the flow knobs listed below, by writing them to `/work/knobs.json`:

```json
{"CORE_UTILIZATION": 60, "PLACE_DENSITY_LB_ADDON": 0.1}
```

Permitted knobs and ranges:

```
  CELL_PAD_IN_SITES_DETAIL_PLACEMENT     int    [0, 3]
  CELL_PAD_IN_SITES_GLOBAL_PLACEMENT     int    [0, 3]
  CORE_MARGIN                            int    [1, 3]
  CORE_UTILIZATION                       int    [30, 85]
  CTS_CLUSTER_DIAMETER                   int    [20, 400]
  CTS_CLUSTER_SIZE                       int    [10, 200]
  PLACE_DENSITY                          float  [0.3, 0.95]
  PLACE_DENSITY_LB_ADDON                 float  [0.0, 0.2]
```

You may **not** edit the RTL, the SDC, or any variable outside this list.
Anything else in `knobs.json` fails the run.

## Budget
You may run the flow at most **12** times. A run takes about 40 seconds.
Runs are counted from your container, so plan your search.

## How you will be judged

**Gates** (all must hold, or the run scores zero):
- the flow completes, with zero DRC, antenna and placement violations
- sign-off timing is no worse than the baseline, re-timed against the design's
  own constraints -- which you cannot change
- every knob you set is inside the permitted space
- you stayed within the run budget

**Score** (only if the gates hold): die area reduction, with power reported
alongside.

Note that timing is a **gate, not a score**. Shrinking the die until timing
degrades earns nothing. Note also that pushing a knob too far can make the
flow fail outright, which scores zero -- the permitted range is wider than the
range that works.

## Deliverable
`/work/knobs.json` is the ONLY thing collected, read exactly as you leave it
whenever you stop -- including if you run out of turns.

Write your best-so-far knobs to it **after every trial**, not at the end. Never
leave the file holding a configuration you have already shown to be worse.
