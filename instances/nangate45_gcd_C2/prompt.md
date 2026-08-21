# Task: missing input delay

## Design
- Platform: `nangate45`
- Design: `gcd`
- Flow: OpenROAD-flow-scripts, RTL-to-GDS

## What you are given
`impl.sdc` -- the timing constraints this design is currently built with.

## What to do
This SDC is incomplete: some timing paths in the design are not being checked at all. Identify what is missing and restore it.

You may edit **only** `impl.sdc`. Do not modify the RTL, the netlist, the
floorplan, or any flow variable.

## How you will be judged
Your edited `impl.sdc` is used to re-run the full flow. The resulting layout is
then re-timed against a **reference SDC that you are not shown**.

That means loosening or deleting constraints cannot help you: the constraints
used to judge the design are not the ones you edited. A run is only scored on
area and power **after** it passes the correctness gates (flow completes, zero
DRC, and sign-off timing no worse than the baseline).
