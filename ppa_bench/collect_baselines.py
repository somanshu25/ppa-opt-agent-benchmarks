"""Collect the default-config QoR baseline for every design explored.

These are the reference numbers every claim in `docs/FINDINGS.md` is stated
against, so they are checked into the repository rather than left in a
container. Preserving them also makes the negative results reproducible: the
sky130hd/gcd baseline is the evidence that its -1.62 ns worst slack is
upstream-intended rather than a broken environment.
"""

from __future__ import annotations

import argparse
import json
import os

from ppa_bench.metrics import parse_run

FLOW = "/OpenROAD-flow-scripts/flow"

# (platform, design, variant, note). The variant is always a default-config run.
DESIGNS = [
    ("nangate45", "gcd", "base",
     "primary benchmark design; timing-clean baseline"),
    ("nangate45", "aes", "base",
     "generalisation target; 524 s/run, no SYNTH_REPEATABLE_BUILD"),
    ("nangate45", "ibex", "base",
     "explored, not benchmarked -- runtime not characterised"),
    ("sky130hd", "gcd", "base",
     "intentionally over-constrained upstream; excluded from v1 scope (F2)"),
]

# The four thread-count repeats behind the determinism claim (F1).
NOISE = [("nangate45", "gcd", "noise_ng45_c{}".format(n)) for n in (1, 2, 4, 8)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="/ppa-bench/results/baselines")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    index = []
    for platform, design, variant, note in DESIGNS:
        try:
            rec = parse_run(FLOW, platform, design, variant)
        except FileNotFoundError:
            print("  MISSING {}/{} [{}]".format(platform, design, variant))
            continue
        name = "{}_{}".format(platform, design)
        with open(os.path.join(args.out, name + ".json"), "w") as fh:
            json.dump({"platform": platform, "design": design,
                       "variant": variant, "note": note,
                       "completed": rec.completed, "qor": rec.qor},
                      fh, indent=2, sort_keys=True)
        q = rec.qor
        index.append({"design": name, "note": note, **{
            k: q.get(k) for k in ("setup_ws", "setup_tns", "inst_area",
                                  "die_area", "power_total", "drc_errors",
                                  "inst_count")}})
        print("  {:20} ws={:+.5f} tns={:+.4f} die={:>8.0f} inst={:>9.1f} drc={}".format(
            name, q["setup_ws"], q["setup_tns"], q["die_area"] or 0,
            q["inst_area"], q["drc_errors"]))

    # Determinism evidence: the four repeats must be identical, so store the
    # comparison rather than four near-copies of the same numbers.
    noise = []
    for platform, design, variant in NOISE:
        try:
            noise.append((variant, parse_run(FLOW, platform, design, variant).qor))
        except FileNotFoundError:
            pass
    if noise:
        keys = sorted(noise[0][1])
        differing = [k for k in keys
                     if len({json.dumps(q.get(k)) for _, q in noise}) > 1]
        with open(os.path.join(args.out, "determinism_nangate45_gcd.json"), "w") as fh:
            json.dump({"variants": [v for v, _ in noise],
                       "note": "NUM_CORES 1/2/4/8, isolated FLOW_VARIANTs",
                       "differing_qor_keys": differing,
                       "qor": noise[0][1]}, fh, indent=2, sort_keys=True)
        print("\n  determinism: {} repeats, {} differing QoR keys {}".format(
            len(noise), len(differing), differing or "(none)"))

    with open(os.path.join(args.out, "index.json"), "w") as fh:
        json.dump(index, fh, indent=2, sort_keys=True)
    print("\n-> {}".format(args.out))


if __name__ == "__main__":
    main()
