# Task: io overconstrain

## Design
- Platform: `nangate45`
- Design: `gcd`
- Flow: OpenROAD-flow-scripts (RTL to GDS)

## What you are given
`impl.sdc` -- the timing constraints this design is currently built with.
You can build the design and inspect its QoR with the OpenROAD flow.

## What to do
This design meets timing and passes signoff, but its QoR is worse than it needs to be. Find the constraint that is costing area and power without buying anything, and improve it.

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
