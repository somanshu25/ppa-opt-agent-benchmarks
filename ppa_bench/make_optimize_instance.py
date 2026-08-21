"""Build an HP-C optimisation instance.

Much simpler than a repair instance, because there is no hidden answer to
protect.  Nothing is injected and nothing is randomised: the agent is handed
the design's own default configuration and asked to beat it.  The reference is
public by construction.

What still needs measuring is the **baseline** -- the die area, power and
sign-off timing of the default config -- because that is what the improvement
threshold and the correctness gates are stated against.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil

from ppa_bench.knobs import load_space, describe

FLOW = "/OpenROAD-flow-scripts/flow"

PROMPT = """# Task: shrink the die

## Design
- Platform: `{platform}`
- Design: `{design}`
- Flow: OpenROAD-flow-scripts (RTL to GDS)

## Goal
This design already builds correctly and meets timing. It is also **larger than
it needs to be**. Make the die smaller by tuning flow knobs.

You must reduce `finish__design__die__area` by at least **{min_pct}%** relative
to the default configuration, **without** regressing correctness.

## What you may change
Only the flow knobs listed below, by writing them to `/work/knobs.json`:

```json
{{"CORE_UTILIZATION": 60, "PLACE_DENSITY_LB_ADDON": 0.1}}
```

Permitted knobs and ranges:

```
{space}
```

You may **not** edit the RTL, the SDC, or any variable outside this list.
Anything else in `knobs.json` fails the run.

## Budget
You may run the flow at most **{budget}** times. A run takes about 40 seconds.
Runs are counted from your container, so plan your search.

## How you will be judged

**Gates** (all must hold, or the run scores zero):
- the flow completes, with zero DRC, antenna and placement violations
- **sign-off timing still closes**: setup worst-slack, setup TNS and hold
  worst-slack must all be `>= 0` when the design is re-timed against its own
  constraints, which you cannot change
- every knob you set is inside the permitted space
- you stayed within the run budget

Note carefully what the timing gate does **not** say. It does not require slack
to be as good as the baseline. You are explicitly permitted to **spend** slack
to buy area: a configuration with worst-slack `+0.002` scores exactly as well
on timing as one with `+0.020`, so long as both are non-negative. Holding back
to preserve baseline slack will cost you area for no benefit.

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
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--platform", default="nangate45")
    ap.add_argument("--design", default="gcd")
    ap.add_argument("--config", default="./designs/nangate45/gcd/config.mk")
    ap.add_argument("--budget", type=int, default=12)
    ap.add_argument("--min-pct", type=float, default=2.0)
    ap.add_argument("--out", default="/ppa-bench/instances")
    args = ap.parse_args()

    space = load_space(FLOW, args.platform, args.design)
    inst_id = "{}_{}_HPC".format(args.platform, args.design)
    inst_dir = os.path.join(args.out, inst_id)
    pub, priv = os.path.join(inst_dir, "public"), os.path.join(inst_dir, "private")
    shutil.rmtree(inst_dir, ignore_errors=True)
    os.makedirs(pub)
    os.makedirs(priv)

    manifest = {
        "instance_id": inst_id,
        "problem": "HP-C",
        "task": "minimise die area under correctness gates",
        "platform": args.platform,
        "design": args.design,
        "design_config": args.config,
        "orfs_commit": "02ba50d53",
        "editable_files": ["knobs.json"],
        "knob_space": space,
        "run_budget": args.budget,
        "min_improvement_pct": args.min_pct,
        # Unlike repair instances there is no hidden reference, so the whole
        # manifest is public.
    }

    with open(os.path.join(pub, "instance.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    with open(os.path.join(pub, "knobs.json"), "w") as fh:
        fh.write("{}\n")   # start from the default config
    with open(os.path.join(pub, "prompt.md"), "w") as fh:
        fh.write(PROMPT.format(
            platform=args.platform, design=args.design,
            min_pct=args.min_pct, budget=args.budget, space=describe(space)))

    # The reference optimum is recorded privately for analysis only. It is not
    # used in grading -- an agent that finds a different equally good
    # configuration must score the same.
    with open(os.path.join(priv, "reference.md"), "w") as fh:
        fh.write(
            "# Reference optimum (analysis only, not used in grading)\n\n"
            "Measured by sweep on nangate45/gcd:\n\n"
            "| CORE_UTILIZATION | die area | delta | ws | drc |\n"
            "|---|---|---|---|---|\n"
            "| 55 (default) | 1278 | 0.00% | +0.01601 | 0 |\n"
            "| 75 | 955 | -25.29% | +0.01040 | 0 |\n"
            "| 77 | 932 | **-27.09%** | +0.01101 | 0 |\n"
            "| 78+ | FAIL | - | - | FLW-0024 in global placement |\n\n"
            "Best legal setting is CORE_UTILIZATION=77. The permitted range "
            "extends to 85 so the optimum is interior and overshooting costs "
            "the run.\n\nFive of the eight permitted knobs are inert on this "
            "design; see docs/FINDINGS.md F11.\n")

    print("created {}".format(inst_dir))
    print("  budget: {} runs, threshold: {}% die-area reduction".format(
        args.budget, args.min_pct))
    print("  knob space:\n{}".format(describe(space)))


if __name__ == "__main__":
    main()
