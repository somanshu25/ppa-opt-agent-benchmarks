"""Grade an HP-B optimisation submission.

Same discipline as the repair grader: the agent's own run directory is never
trusted. The flow is re-run from clean with exactly the submitted knobs, and
the resulting layout is re-timed against the design's own constraints -- which
the agent was not permitted to touch, so they serve as the held-out reference
without needing to be hidden.
"""

from __future__ import annotations

import argparse
import json
import os

from ppa_bench.metrics import parse_run
from ppa_bench import grader, baseline, knobs as knobmod
from ppa_bench.optimize import grade_optimize, Budget
from ppa_bench.validate import run_signoff, FLOW
import subprocess

BASELINE_VARIANT = "hpb_base"


def run_flow_knobs(config: str, variant: str, knob_args: list, log: str) -> None:
    with open(log, "w") as fh:
        subprocess.call(
            ["make", "DESIGN_CONFIG=" + config, "FLOW_VARIANT=" + variant] + knob_args,
            cwd=FLOW, stdout=fh, stderr=subprocess.STDOUT)


def ensure_baseline(inst_dir: str, pub: dict, work: str) -> dict:
    """Measure and freeze the default-config baseline, once."""
    frozen = baseline.load(inst_dir)
    if frozen is not None:
        return frozen

    platform, design = pub["platform"], pub["design"]
    config = pub["design_config"]
    sdc = os.path.join(FLOW, "designs", platform, design, "constraint.sdc")

    print("  [baseline] running default config ...", flush=True)
    run_flow_knobs(config, BASELINE_VARIANT, [],
                   os.path.join(work, BASELINE_VARIANT + ".log"))
    run = parse_run(FLOW, platform, design, BASELINE_VARIANT)
    so = grader.signoff_view(run_signoff(
        config, BASELINE_VARIANT, sdc,
        os.path.join(work, BASELINE_VARIANT + ".signoff.json")))
    # freeze() enforces the sign-off self-test: golden == the SDC the flow ran
    # with, so the two must agree exactly.
    return baseline.freeze(inst_dir, run.qor, so, BASELINE_VARIANT,
                           {"knobs": "default"}, run.completed)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("instance")
    ap.add_argument("submission", help="path to the agent's knobs.json")
    ap.add_argument("--runs-used", type=int, default=None)
    ap.add_argument("--tag", default="hpb")
    ap.add_argument("--work", default="/tmp/ppa_hpb")
    ap.add_argument("--out", default="/ppa-bench/results/hpb_runs.json")
    args = ap.parse_args()

    inst_dir = os.path.abspath(args.instance)
    pub = json.load(open(os.path.join(inst_dir, "public", "instance.json")))
    platform, design, config = pub["platform"], pub["design"], pub["design_config"]
    sdc = os.path.join(FLOW, "designs", platform, design, "constraint.sdc")
    os.makedirs(args.work, exist_ok=True)

    frozen = ensure_baseline(inst_dir, pub, args.work)

    space = knobmod.load_space(FLOW, platform, design)
    submission = knobmod.load_submission(os.path.abspath(args.submission))
    violations = knobmod.validate(submission, space)
    print("  submitted knobs: {}".format(submission or "(none -- default config)"))
    if violations:
        print("  knob violations: {}".format("; ".join(violations)))

    # Re-run with exactly what was submitted. Illegal knobs are NOT passed to
    # make -- the violation is already recorded, and forwarding them would let
    # a rejected submission still influence the measurement.
    variant = "{}_{}".format(args.tag, pub["instance_id"])
    knob_args = [] if violations else knobmod.to_make_args(submission, space)
    print("  re-running flow with {} ...".format(knob_args or "default config"),
          flush=True)
    run_flow_knobs(config, variant, knob_args, os.path.join(args.work, variant + ".log"))

    try:
        run = parse_run(FLOW, platform, design, variant)
        run_qor, completed = run.qor, run.completed
    except FileNotFoundError:
        run_qor, completed = {}, False

    print("  sign-off against the design's own constraints ...", flush=True)
    run_so = grader.signoff_view(run_signoff(
        config, variant, sdc, os.path.join(args.work, variant + ".signoff.json")))

    budget = None
    if args.runs_used is not None:
        budget = Budget(allowed=pub["run_budget"], used=args.runs_used)

    verdict = grade_optimize(
        "{} [{}]".format(pub["instance_id"], args.tag),
        run_qor, run_so, frozen["qor"], frozen["signoff"], completed,
        knobs_set=set(submission), knob_violations=violations,
        budget=budget, min_improvement_pct=pub["min_improvement_pct"])

    print()
    print(verdict.report())

    base_die = frozen["qor"].get("die_area")
    print("\nbaseline die area {:.0f} -> submitted {}".format(
        base_die,
        "{:.0f}".format(run_qor["die_area"]) if run_qor.get("die_area") else "FAILED"))

    result = {
        "instance_id": pub["instance_id"],
        "tag": args.tag,
        "submitted_knobs": submission,
        "knob_violations": violations,
        "resolved": verdict.resolved,
        "failed_assertions": [a.name for a in verdict.assertions if not a.passed],
        "score": verdict.score,
        "baseline_die_area": base_die,
        "die_area": run_qor.get("die_area"),
        "runs_used": args.runs_used,
        "run_budget": pub["run_budget"],
        "report": verdict.report(),
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    existing = []
    if os.path.isfile(args.out):
        try:
            existing = json.load(open(args.out))
        except json.JSONDecodeError:
            existing = []
    existing = [r for r in existing if r.get("tag") != args.tag]
    existing.append(result)
    with open(args.out, "w") as fh:
        json.dump(existing, fh, indent=2, sort_keys=True)
    print("\n-> {}".format(args.out))


if __name__ == "__main__":
    main()
