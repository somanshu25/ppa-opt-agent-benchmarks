"""Materialise benchmark instances on disk, one directory per (design, class).

Each instance directory is self-contained and holds the two-SDC pair the whole
benchmark turns on:

    impl.sdc    the mutated constraints -- this is what the agent sees and edits
    golden.sdc  the reference constraints -- held out, used only for sign-off

plus the task prompt, the ground-truth fix, and a machine-readable manifest.

Generating an instance is cheap and says nothing about whether it is a *good*
task.  That is what validation decides (see docs/PLAN.md, W5): an instance is
only shippable once the broken version measurably fails and the reference fix
measurably recovers.  Every manifest therefore starts at
``"validated": false``.
"""

from __future__ import annotations

import argparse
import json
import os

from ppa_bench.injector import inject, V1_CLASSES, InjectionError

# (platform, design_dir, config.mk path relative to flow/)
DESIGNS = [
    ("nangate45", "gcd", "./designs/nangate45/gcd/config.mk"),
    ("nangate45", "aes", "./designs/nangate45/aes/config.mk"),
    ("nangate45", "ibex", "./designs/nangate45/ibex/config.mk"),
    ("sky130hd", "gcd", "./designs/sky130hd/gcd/config.mk"),
]

# Designs whose baseline is timing-clean enough to support gate-based grading.
# sky130hd/gcd is excluded on purpose: upstream itself expects WS -1.68 /
# TNS -71.2 there, so a "no violations" gate would fail the baseline and an
# injected defect would be swamped by the existing violation floor.
V1_DESIGNS = {("nangate45", "gcd"), ("nangate45", "aes")}

PROMPT_TEMPLATE = """# Task: {title}

## Design
- Platform: `{platform}`
- Design: `{design}`
- Flow: OpenROAD-flow-scripts, RTL-to-GDS

## What you are given
`impl.sdc` -- the timing constraints this design is currently built with.

## What to do
{description}

You may edit **only** `impl.sdc`. Do not modify the RTL, the netlist, the
floorplan, or any flow variable.

## How you will be judged
Your edited `impl.sdc` is used to re-run the full flow. The resulting layout is
then re-timed against a **reference SDC that you are not shown**.

That means loosening or deleting constraints cannot help you: the constraints
used to judge the design are not the ones you edited. A run is only scored on
area and power **after** it passes the correctness gates (flow completes, zero
DRC, and sign-off timing no worse than the baseline).
"""


def build(class_id: str, platform: str, design: str, config: str,
          flow_dir: str, out_root: str) -> dict | None:
    """Generate one instance directory; return its manifest (or None if N/A)."""
    sdc_path = os.path.join(flow_dir, "designs", platform, design, "constraint.sdc")
    if not os.path.isfile(sdc_path):
        print("  SKIP {}/{} {}: no constraint.sdc".format(platform, design, class_id))
        return None

    golden = open(sdc_path).read()
    try:
        inj = inject(class_id, golden)
    except InjectionError as exc:
        print("  SKIP {}/{} {}: {}".format(platform, design, class_id, exc))
        return None

    inst_id = "{}_{}_{}".format(platform, design, class_id)
    inst_dir = os.path.join(out_root, inst_id)
    os.makedirs(inst_dir, exist_ok=True)

    with open(os.path.join(inst_dir, "impl.sdc"), "w") as fh:
        fh.write(inj.sdc)
    with open(os.path.join(inst_dir, "golden.sdc"), "w") as fh:
        fh.write(inj.golden_sdc)
    with open(os.path.join(inst_dir, "prompt.md"), "w") as fh:
        fh.write(PROMPT_TEMPLATE.format(
            title=inj.name.replace("_", " "),
            platform=platform,
            design=design,
            description=inj.description,
        ))
    with open(os.path.join(inst_dir, "ground_truth.md"), "w") as fh:
        fh.write("# Ground truth: {}\n\n".format(inst_id))
        fh.write("**Injected defect:** {}\n\n".format(inj.notes))
        fh.write("**Reference fix restores:**\n\n```\n{}\n```\n".format(inj.ground_truth))

    manifest = {
        "instance_id": inst_id,
        "class_id": inj.class_id,
        "class_name": inj.name,
        "platform": platform,
        "design": design,
        "design_config": config,
        "orfs_commit": "02ba50d53",
        "editable_files": ["impl.sdc"],
        "golden_sdc": "golden.sdc",
        "silent_defect": inj.silent,
        "expect_degrades": inj.expect_degrades,
        "notes": inj.notes,
        "in_v1_scope": (platform, design) in V1_DESIGNS and class_id in V1_CLASSES,
        # Set by validate.py once BROKEN_FAIL / REFFIX_PASS are demonstrated.
        "validated": False,
    }
    with open(os.path.join(inst_dir, "instance.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)

    scope = "v1" if manifest["in_v1_scope"] else "--"
    print("  {:34} {:3} silent={:5} [{}]".format(
        inst_id, inj.class_id, str(inj.silent), scope))
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--flow-dir", default="/OpenROAD-flow-scripts/flow")
    ap.add_argument("--out", default="/ppa-bench/instances")
    ap.add_argument("--classes", nargs="*", default=V1_CLASSES + ["CX"])
    args = ap.parse_args()

    print("Generating instances into {}\n".format(args.out))
    manifests = []
    for platform, design, config in DESIGNS:
        print("{}/{}:".format(platform, design))
        for class_id in args.classes:
            m = build(class_id, platform, design, config, args.flow_dir, args.out)
            if m:
                manifests.append(m)
        print()

    index_path = os.path.join(args.out, "index.json")
    with open(index_path, "w") as fh:
        json.dump(manifests, fh, indent=2, sort_keys=True)

    v1 = sum(1 for m in manifests if m["in_v1_scope"])
    print("{} instances generated ({} in v1 scope, all validated=false)".format(
        len(manifests), v1))
    print("index -> {}".format(index_path))


if __name__ == "__main__":
    main()
