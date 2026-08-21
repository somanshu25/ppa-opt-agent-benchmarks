"""Materialise benchmark instances with a hard public/private split.

Layout, one directory per (design, class, seed):

    <instance_id>/
        public/          <- the ONLY thing that enters the agent's container
            impl.sdc         the mutated constraints; the agent edits this
            prompt.md        the task
            instance.json    metadata with no answers in it
        private/         <- never mounted, never copied in during the run
            golden.sdc       reference constraints, used only for sign-off
            ground_truth.md  the reference fix
            answer.json      sampled parameters + expected degradations

Two independent safeguards, defending against two different threats:

1. **Partitioning** stops the agent reading the answer out of the instance.
   Necessary, but on its own unfalsifiable -- upstream's pristine
   ``constraint.sdc``, git history and stale ``6_final.sdc`` files all leak the
   same value, and you can never prove you found every path.

2. **Randomisation** (``randomize.py``) makes the leaked value *wrong*. The
   golden is drawn at generation time, so no copy of upstream and no memorised
   training data yields it.

Neither replaces the sign-off gate: that defends against gaming the grader,
which is a different attack from finding the answer.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil

from ppa_bench.injector import inject, V1_CLASSES, InjectionError
from ppa_bench.randomize import sample_params, render_golden

DESIGNS = {
    ("nangate45", "gcd"): "./designs/nangate45/gcd/config.mk",
    ("nangate45", "aes"): "./designs/nangate45/aes/config.mk",
}

PROMPT_TEMPLATE = """# Task: {title}

## Design
- Platform: `{platform}`
- Design: `{design}`
- Flow: OpenROAD-flow-scripts (RTL to GDS)

## What you are given
`impl.sdc` -- the timing constraints this design is currently built with.
You can build the design and inspect its QoR with the OpenROAD flow.

## What to do
{description}

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
"""


def build(class_id, platform, design, config, seed, flow_dir, out_root):
    """Generate one instance directory. Returns its public manifest."""
    template_path = os.path.join(
        flow_dir, "designs", platform, design, "constraint.sdc")
    if not os.path.isfile(template_path):
        print("  SKIP {}/{} {}: no constraint.sdc".format(platform, design, class_id))
        return None

    # Randomise first: the golden is the *sampled* SDC, not upstream's.
    params = sample_params(platform, design, seed)
    golden = render_golden(open(template_path).read(), params)

    try:
        inj = inject(class_id, golden)
    except InjectionError as exc:
        print("  SKIP {}/{} {}: {}".format(platform, design, class_id, exc))
        return None

    inst_id = "{}_{}_{}_s{}".format(platform, design, class_id, seed)
    inst_dir = os.path.join(out_root, inst_id)
    pub = os.path.join(inst_dir, "public")
    priv = os.path.join(inst_dir, "private")
    shutil.rmtree(inst_dir, ignore_errors=True)
    os.makedirs(pub)
    os.makedirs(priv)

    manifest = {
        "instance_id": inst_id,
        "class_id": inj.class_id,
        "class_name": inj.name,
        "platform": platform,
        "design": design,
        "design_config": config,
        "orfs_commit": "02ba50d53",
        "editable_files": ["impl.sdc"],
        # Deliberately absent from the public manifest: the sampled parameter
        # values, expect_degrades, silent_defect -- and the seed. The sampler
        # ships with the benchmark, so seed + public code would recompute the
        # golden directly were it not for the sampling secret; omitting the
        # seed as well is defence in depth.
    }

    answer = {
        "instance_id": inst_id,
        "clk_period": params.clk_period,
        "clk_io_pct": params.clk_io_pct,
        "seed": seed,
        "silent_defect": inj.silent,
        "expect_degrades": inj.expect_degrades,
        "ground_truth": inj.ground_truth,
        "notes": inj.notes,
        # Set by validate.py once BASELINE_PASS and BROKEN_FAIL are shown.
        "validated": False,
    }

    _write(os.path.join(pub, "impl.sdc"), inj.sdc)
    _write(os.path.join(pub, "prompt.md"), PROMPT_TEMPLATE.format(
        title=inj.name.replace("_", " "),
        platform=platform, design=design, description=inj.description))
    _write(os.path.join(pub, "instance.json"), json.dumps(manifest, indent=2, sort_keys=True))

    _write(os.path.join(priv, "golden.sdc"), inj.golden_sdc)
    _write(os.path.join(priv, "answer.json"), json.dumps(answer, indent=2, sort_keys=True))
    _write(os.path.join(priv, "ground_truth.md"),
           "# Ground truth: {}\n\n"
           "**Sampled golden:** {}\n\n"
           "**Injected defect:** {}\n\n"
           "**Reference fix restores:**\n\n```\n{}\n```\n".format(
               inst_id, params.describe(), inj.notes, inj.ground_truth))

    print("  {:32} {:3} {:22} silent={:5} {}".format(
        inst_id, inj.class_id, inj.name, str(inj.silent), params.describe()))
    return manifest


def _write(path: str, text: str) -> None:
    with open(path, "w") as fh:
        fh.write(text)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate benchmark instances")
    ap.add_argument("--flow-dir", default="/OpenROAD-flow-scripts/flow")
    ap.add_argument("--out", default="/ppa-bench/instances")
    ap.add_argument("--classes", nargs="*", default=V1_CLASSES)
    ap.add_argument("--seeds", nargs="*", type=int, default=[1])
    ap.add_argument("--designs", nargs="*", default=["nangate45/gcd"])
    args = ap.parse_args()

    print("Generating into {}\n".format(args.out))
    manifests = []
    for spec in args.designs:
        platform, design = spec.split("/")
        config = DESIGNS[(platform, design)]
        print("{}/{}:".format(platform, design))
        for seed in args.seeds:
            for class_id in args.classes:
                m = build(class_id, platform, design, config, seed,
                          args.flow_dir, args.out)
                if m:
                    manifests.append(m)
        print()

    _write(os.path.join(args.out, "index.json"),
           json.dumps(manifests, indent=2, sort_keys=True))
    print("{} instances generated (all validated=false)".format(len(manifests)))


if __name__ == "__main__":
    main()
