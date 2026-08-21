# Task: missing output delay

## Design
- Platform: `nangate45`
- Design: `gcd`
- Flow: OpenROAD-flow-scripts (RTL to GDS)

## What you are given
`impl.sdc` -- the timing constraints this design is currently built with.
You can build the design and inspect its QoR with the OpenROAD flow.

## What to do
This SDC is incomplete: some timing paths in the design are not being checked at all. Identify what is missing and restore it.

You may edit **only** `impl.sdc`.

## How you will be judged
Your edited `impl.sdc` is used to re-run the full flow from clean. The
resulting layout is then re-timed against a **reference SDC you are not
shown**.

Loosening or deleting constraints therefore cannot help you: the constraints
used to judge the design are not the ones you edited. Your run is scored on
area and power only **after** it passes the correctness gates -- the flow
completes, DRC is clean, and sign-off timing is no worse than the baseline.

Note that the reference constraints for this instance were generated
specifically for it. They are not the values in any public version of this
design.

## Building the design

You have the full OpenROAD flow. Build and inspect QoR with:

    cd /OpenROAD-flow-scripts/flow
    make DESIGN_CONFIG=./designs/nangate45/gcd/config.mk SDC_FILE=/work/impl.sdc FLOW_VARIANT=try1

Use a fresh FLOW_VARIANT name for each attempt. Metrics land in
logs/nangate45/gcd/<variant>/*.json -- 6_report.json has the final timing,
power and area. A run takes about 40 seconds.

## Deliverable

Leave your final constraints at /work/impl.sdc. Nothing else is collected.
