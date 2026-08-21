"""Grade an agent's submitted SDC.

Runs in the grading container, never the agent's. The agent's own run
directory is not trusted or read: the flow is re-run from clean with the
submitted SDC, exactly as SWE-bench re-runs tests from a fresh checkout rather
than believing an agent's reported results.

Sequence, per attempt:

  1. static checks   diff confined to editable files
  2. re-run flow     with the submitted impl.sdc, isolated FLOW_VARIANT
  3. sign-off STA    the resulting layout, re-timed against private/golden.sdc
  4. assertions      P2P from stage metrics, F2P from sign-off only
  5. verdict         resolved = all(P2P) and all(F2P)

The baseline is read from the frozen ``private/baseline.json``, so grading
costs one flow run plus one sign-off -- never a baseline run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from ppa_bench.metrics import parse_run
from ppa_bench import grader, baseline
from ppa_bench.validate import run_flow, run_signoff, FLOW


def grade_submission(inst_dir: str, submitted_sdc: str, work: str,
                     tag: str = "agent") -> dict:
    inst_dir = os.path.abspath(inst_dir)
    submitted_sdc = os.path.abspath(submitted_sdc)
    pub = json.load(open(os.path.join(inst_dir, "public", "instance.json")))
    inst_id, config = pub["instance_id"], pub["design_config"]
    platform, design = pub["platform"], pub["design"]
    golden = os.path.join(inst_dir, "private", "golden.sdc")

    frozen = baseline.load(inst_dir)
    if frozen is None:
        raise SystemExit(
            "{}: no frozen baseline -- run validate.py first".format(inst_id))

    os.makedirs(work, exist_ok=True)
    variant = "{}_{}".format(tag, inst_id)

    print("  re-running flow with the submitted SDC ...", flush=True)
    run_flow(config, variant, submitted_sdc, os.path.join(work, variant + ".log"))

    try:
        run = parse_run(FLOW, platform, design, variant)
        run_qor, completed = run.qor, run.completed
    except FileNotFoundError:
        run_qor, completed = {}, False

    print("  sign-off against the held-out golden SDC ...", flush=True)
    run_so = grader.signoff_view(run_signoff(
        config, variant, golden, os.path.join(work, variant + ".signoff.json")))

    # The agent was given exactly one editable file; anything else is a
    # protocol violation regardless of the metrics.
    verdict = grader.grade(
        "{} [{}]".format(inst_id, tag), run_qor, run_so,
        frozen["qor"], frozen["signoff"], completed,
        edited_files={"impl.sdc"},
        editable_files=set(pub["editable_files"]),
        knobs_set=set())

    submitted = open(submitted_sdc).read()
    golden_text = open(golden).read()
    return {
        "instance_id": inst_id,
        "class_id": pub["class_id"],
        "tag": tag,
        "resolved": verdict.resolved,
        "failed_assertions": [a.name for a in verdict.assertions if not a.passed],
        "score": verdict.score,
        "finish_ws": run_qor.get("setup_ws"),
        "signoff_ws": run_so.get("setup_ws"),
        "baseline_signoff_ws": frozen["signoff"].get("setup_ws"),
        "area": run_qor.get("inst_area"),
        "baseline_area": frozen["qor"].get("inst_area"),
        # Informational only. Grading is behavioural: an agent that writes a
        # different but equally correct constraint must still pass, so this is
        # never an assertion.
        "matches_golden_exactly": submitted.strip() == golden_text.strip(),
        "report": verdict.report(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", nargs="+", required=True,
                    help="instance_dir=submitted_sdc pairs")
    ap.add_argument("--tag", default="agent")
    ap.add_argument("--work", default="/tmp/ppa_agent_grade")
    ap.add_argument("--out", default="/ppa-bench/results/agent_runs.json")
    args = ap.parse_args()

    results = []
    for pair in args.runs:
        inst_dir, sdc = pair.split("=", 1)
        print("\n=== {} ===".format(os.path.basename(inst_dir)), flush=True)
        r = grade_submission(inst_dir, sdc, args.work, args.tag)
        print(r["report"])
        results.append(r)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(results, fh, indent=2, sort_keys=True)

    print("\n" + "=" * 88)
    print("{:16} {:9} {:>9} {:>10} {:>10} {:>8}  {}".format(
        "instance", "resolved", "fin_ws", "signoff_ws", "base_sgn", "area", "failed"))
    print("-" * 88)
    for r in results:
        f = lambda v: "{:.5f}".format(v) if isinstance(v, float) else "-"  # noqa: E731
        print("{:16} {:9} {:>9} {:>10} {:>10} {:>8}  {}".format(
            r["instance_id"].replace("nangate45_gcd_", ""),
            "YES" if r["resolved"] else "no",
            f(r["finish_ws"]), f(r["signoff_ws"]), f(r["baseline_signoff_ws"]),
            f(r["area"]), ",".join(r["failed_assertions"]) or "-"))
    n = sum(1 for r in results if r["resolved"])
    print("\nscore: {}/{} resolved -> {}".format(n, len(results), args.out))


if __name__ == "__main__":
    main()
