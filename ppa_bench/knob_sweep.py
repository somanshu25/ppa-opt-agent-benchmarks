"""Measure how much each flow knob actually moves the objective.

Before an optimisation benchmark can declare "minimise area", the tunable range
has to be measured.  If the permitted knobs only move area by a fraction of a
percent, the improvement threshold has nowhere to live and the objective is the
wrong one -- better to find that out in ten minutes of sweeping than after
building a grader around it.

This is the same discipline that set the clock-period randomisation range: the
number comes from running the flow, not from reading a config file.

One-at-a-time sensitivity: each knob is moved to the ends of its permitted
range with everything else at default.  That misses interactions, which is
fine -- the question here is "does this knob do anything at all", not "what is
the optimum".

Two area metrics are reported because they answer different questions:

``die_area``   the physical footprint, i.e. what silicon actually costs. Driven
               directly by CORE_UTILIZATION.
``inst_area``  the sum of cell areas, largely fixed by synthesis and timing
               repair. Expected to be far less tunable.

A knob value that breaks the flow is recorded rather than hidden: it bounds the
usable range, which the benchmark needs to know.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from ppa_bench.metrics import parse_run
from ppa_bench.knobs import load_space

FLOW = "/OpenROAD-flow-scripts/flow"


def run_point(config: str, variant: str, knobs: dict, work: str) -> list[str]:
    args = ["{}={}".format(k, v) for k, v in sorted(knobs.items())]
    log = os.path.join(work, variant + ".log")
    with open(log, "w") as fh:
        subprocess.call(
            ["make", "DESIGN_CONFIG=" + config, "FLOW_VARIANT=" + variant] + args,
            cwd=FLOW, stdout=fh, stderr=subprocess.STDOUT)
    return args


def measure(platform: str, design: str, variant: str) -> dict:
    try:
        run = parse_run(FLOW, platform, design, variant)
    except FileNotFoundError:
        return {"completed": False}
    q = run.qor
    return {
        "completed": run.completed,
        "die_area": q.get("die_area"),
        "core_area": q.get("core_area"),
        "inst_area": q.get("inst_area"),
        "utilization": q.get("utilization"),
        "power_total": q.get("power_total"),
        "setup_ws": q.get("setup_ws"),
        "drc_errors": q.get("drc_errors"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--platform", default="nangate45")
    ap.add_argument("--design", default="gcd")
    ap.add_argument("--config", default="./designs/nangate45/gcd/config.mk")
    ap.add_argument("--work", default="/tmp/knob_sweep")
    ap.add_argument("--out", default="/ppa-bench/results/knob_sweep.json")
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    space = load_space(FLOW, args.platform, args.design)

    # Points to visit: default, then each knob at both ends. CORE_UTILIZATION
    # gets extra interior points because it is the one knob expected to move
    # die area directly, so its shape matters more than its endpoints.
    points = [("default", {})]
    for name, spec in sorted(space.items()):
        lo, hi = spec["minmax"]
        for tag, val in (("min", lo), ("max", hi)):
            points.append(("{}_{}".format(name, tag), {name: val}))
    for val in (45, 60):
        points.append(("CORE_UTILIZATION_{}".format(val), {"CORE_UTILIZATION": val}))

    results = []
    for i, (tag, knobs) in enumerate(points, 1):
        variant = "sweep_" + tag.lower()
        print("[{}/{}] {} {}".format(i, len(points), tag, knobs or "(default)"),
              flush=True)
        run_point(args.config, variant, knobs, args.work)
        rec = measure(args.platform, args.design, variant)
        rec.update({"tag": tag, "knobs": knobs, "variant": variant})
        results.append(rec)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(results, fh, indent=2, sort_keys=True)

    base = next((r for r in results if r["tag"] == "default"), None)
    if not base or not base.get("completed"):
        print("\nbaseline did not complete; nothing to compare against")
        sys.exit(1)

    print("\n" + "=" * 96)
    print("baseline: die={:.0f} inst={:.1f} power={:.4f}mW ws={:+.5f}".format(
        base["die_area"], base["inst_area"], base["power_total"] * 1000,
        base["setup_ws"]))
    print("=" * 96)
    print("{:38} {:>10} {:>10} {:>10} {:>9} {:>6}".format(
        "knob point", "die %", "inst %", "power %", "ws", "ok"))
    print("-" * 96)

    def pct(new, old):
        return 100.0 * (new - old) / old if old else float("nan")

    rows = []
    for r in results:
        if r["tag"] == "default":
            continue
        if not r.get("completed"):
            rows.append((0.0, "{:38} {:>10} {:>10} {:>10} {:>9} {:>6}".format(
                r["tag"], "-", "-", "-", "-", "FAIL")))
            continue
        d = pct(r["die_area"], base["die_area"])
        rows.append((abs(d), "{:38} {:>+10.2f} {:>+10.2f} {:>+10.2f} {:>+9.5f} {:>6}".format(
            r["tag"], d, pct(r["inst_area"], base["inst_area"]),
            pct(r["power_total"], base["power_total"]), r["setup_ws"],
            "ok" if r["drc_errors"] == 0 else "DRC")))

    for _, line in sorted(rows, key=lambda x: -x[0]):
        print(line)

    ok = [r for r in results if r.get("completed") and r["tag"] != "default"]
    if ok:
        die = [pct(r["die_area"], base["die_area"]) for r in ok]
        inst = [pct(r["inst_area"], base["inst_area"]) for r in ok]
        print("\nrange over permitted knobs:")
        print("  die_area  {:+.2f}% .. {:+.2f}%".format(min(die), max(die)))
        print("  inst_area {:+.2f}% .. {:+.2f}%".format(min(inst), max(inst)))
    print("\n-> {}".format(args.out))


if __name__ == "__main__":
    main()
