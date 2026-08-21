"""Instance validation: the SWE-bench FAIL-to-PASS analogue.

Generating an instance is free and proves nothing.  An instance is only
shippable once it has been *demonstrated* to be a real task:

* ``BASELINE_PASS`` -- the clean golden SDC produces a run that satisfies every
  gate.  If the baseline itself cannot pass, no agent can, and the gates are
  measuring the design rather than the agent.
* ``BROKEN_FAIL``  -- the injected SDC produces a run that fails at least one
  assertion.  If the broken run passes, there is no defect to find and the
  instance is vacuous.  This is not hypothetical: it is exactly how the CX
  class died (docs/FINDINGS.md F5).
* ``REFFIX_PASS``  -- applying the reference fix restores the gates.  For these
  classes the reference fix restores the golden SDC exactly, so the fixed run
  *is* the baseline run; it is reported for completeness rather than re-run.

Only ``BROKEN_FAIL`` carries real information, so it is the number to look at.

Cost note: the baseline is shared by every class at a given (design, seed), so
validating N classes costs 1 + N flow runs, not 3N.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from ppa_bench.metrics import parse_run
from ppa_bench import grader

FLOW = "/OpenROAD-flow-scripts/flow"
SIGNOFF = "/ppa-bench/bin/signoff.sh"


def run_flow(config: str, variant: str, sdc: str, log: str) -> bool:
    """Run the ORFS flow with a specific SDC into an isolated flow variant."""
    cmd = ["make", "DESIGN_CONFIG=" + config, "FLOW_VARIANT=" + variant,
           "SDC_FILE=" + sdc]
    with open(log, "w") as fh:
        rc = subprocess.call(cmd, cwd=FLOW, stdout=fh, stderr=subprocess.STDOUT)
    return rc == 0


def run_signoff(config: str, variant: str, golden: str, out: str) -> dict:
    """Re-time an existing run's final layout against the golden SDC."""
    rc = subprocess.call([SIGNOFF, config, variant, golden, out],
                         stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    if rc != 0 or not os.path.isfile(out):
        return {}
    with open(out) as fh:
        return json.load(fh)


def validate_instance(inst_dir: str, work: str) -> dict:
    """Validate one instance; returns a result record."""
    # The flow subprocess runs with cwd=FLOW, so every path handed to make
    # must be absolute.
    inst_dir = os.path.abspath(inst_dir)
    pub = json.load(open(os.path.join(inst_dir, "public", "instance.json")))
    ans = json.load(open(os.path.join(inst_dir, "private", "answer.json")))
    inst_id = pub["instance_id"]
    config = pub["design_config"]
    platform, design = pub["platform"], pub["design"]
    seed = ans["seed"]

    golden = os.path.join(inst_dir, "private", "golden.sdc")
    impl = os.path.join(inst_dir, "public", "impl.sdc")

    # The baseline depends only on (design, seed), so it is shared across the
    # classes generated from the same golden and only ever run once.
    base_variant = "val_base_{}_{}_s{}".format(platform, design, seed)
    broken_variant = "val_{}".format(inst_id)

    os.makedirs(work, exist_ok=True)

    base_log_dir = os.path.join(FLOW, "logs", platform, design, base_variant)
    if not os.path.isdir(base_log_dir):
        print("  [baseline] running {} ...".format(base_variant), flush=True)
        run_flow(config, base_variant, golden,
                 os.path.join(work, base_variant + ".log"))
    else:
        print("  [baseline] reusing {}".format(base_variant), flush=True)

    print("  [broken]   running {} ...".format(broken_variant), flush=True)
    run_flow(config, broken_variant, impl,
             os.path.join(work, broken_variant + ".log"))

    base_run = parse_run(FLOW, platform, design, base_variant)
    broken_run = parse_run(FLOW, platform, design, broken_variant)

    base_so = grader.signoff_view(run_signoff(
        config, base_variant, golden, os.path.join(work, base_variant + ".signoff.json")))
    broken_so = grader.signoff_view(run_signoff(
        config, broken_variant, golden,
        os.path.join(work, broken_variant + ".signoff.json")))

    # BASELINE_PASS: grade the baseline against itself. Every gate must hold.
    v_base = grader.grade(inst_id + " [baseline]", base_run.qor, base_so,
                          base_run.qor, base_so, base_run.completed)

    # BROKEN_FAIL: grade the injected run against the baseline. Must NOT pass.
    v_broken = grader.grade(inst_id + " [broken]", broken_run.qor, broken_so,
                            base_run.qor, base_so, broken_run.completed)

    failed = [a.name for a in v_broken.assertions if not a.passed]
    record = {
        "instance_id": inst_id,
        "class_id": pub["class_id"],
        "seed": seed,
        "golden": {"clk_period": ans["clk_period"], "clk_io_pct": ans["clk_io_pct"]},
        "BASELINE_PASS": v_base.resolved,
        "BROKEN_FAIL": not v_broken.resolved,
        "REFFIX_PASS": v_base.resolved,   # reference fix restores golden exactly
        "broken_failed_assertions": failed,
        "silent_defect": ans["silent_defect"],
        "evidence": {
            # The pair that shows the inversion for silent classes: the flow's
            # own view versus the held-out sign-off view.
            "baseline_finish_ws": base_run.qor.get("setup_ws"),
            "broken_finish_ws": broken_run.qor.get("setup_ws"),
            "baseline_signoff_ws": base_so.get("setup_ws"),
            "broken_signoff_ws": broken_so.get("setup_ws"),
            "baseline_signoff_tns": base_so.get("setup_tns"),
            "broken_signoff_tns": broken_so.get("setup_tns"),
            "baseline_area": base_run.qor.get("inst_area"),
            "broken_area": broken_run.qor.get("inst_area"),
            "baseline_power": base_run.qor.get("power_total"),
            "broken_power": broken_run.qor.get("power_total"),
        },
    }
    record["validated"] = record["BASELINE_PASS"] and record["BROKEN_FAIL"]

    # Persist the verdict alongside the instance so the evidence travels with it.
    with open(os.path.join(inst_dir, "private", "validation.json"), "w") as fh:
        json.dump({"record": record,
                   "baseline_verdict": v_base.to_dict(),
                   "broken_verdict": v_broken.to_dict()}, fh, indent=2, sort_keys=True)

    ans["validated"] = record["validated"]
    with open(os.path.join(inst_dir, "private", "answer.json"), "w") as fh:
        json.dump(ans, fh, indent=2, sort_keys=True)

    return record


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("instances", nargs="+")
    ap.add_argument("--work", default="/tmp/ppa_validate")
    ap.add_argument("--out", default="/ppa-bench/results/validation.json")
    args = ap.parse_args()

    records = []
    for inst_dir in args.instances:
        print("\n=== {} ===".format(os.path.basename(inst_dir)), flush=True)
        records.append(validate_instance(inst_dir, args.work))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(records, fh, indent=2, sort_keys=True)

    print("\n" + "=" * 78)
    print("{:34} {:>6} {:>6} {:>6}  {}".format(
        "instance", "BASE", "BROKE", "VALID", "broken failed on"))
    print("-" * 78)
    for r in records:
        print("{:34} {:>6} {:>6} {:>6}  {}".format(
            r["instance_id"],
            "PASS" if r["BASELINE_PASS"] else "FAIL",
            "FAIL" if r["BROKEN_FAIL"] else "pass",
            "yes" if r["validated"] else "NO",
            ",".join(r["broken_failed_assertions"]) or "-"))
    n = sum(1 for r in records if r["validated"])
    print("\n{}/{} instances validated -> {}".format(n, len(records), args.out))
    sys.exit(0 if n else 1)


if __name__ == "__main__":
    main()
