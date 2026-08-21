"""Decoy agents: prove the grader cannot be gamed, and that it can be passed.

Instance validation (``validate.py``) only ever compares a clean baseline
against an injected run.  No agent is involved, so several assertions never
fire -- ``edits_confined``, ``no_disabled_checks``, and every code path that
depends on a *missing* metric.  Those are untested until something actually
attacks them.

Four scripted agents, three adversarial and one honest:

``oracle``      restores the golden SDC.  **Must RESOLVE.**  The positive
                control: without it, a grader that fails everything would look
                perfectly secure.
``null``        changes nothing.  Must not resolve -- otherwise the instance
                is vacuous.
``cheat_loose`` relaxes the clock period massively.  Its own run reports
                excellent slack; sign-off against the golden SDC must reject
                it.  This is the attack the whole benchmark exists to stop.
``cheat_knob``  submits a correct SDC but disables detailed routing, so no DRC
                and no parasitics are ever produced.  Must not resolve.
                Absence of evidence must fail, never pass.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

from ppa_bench.metrics import parse_run
from ppa_bench import grader
from ppa_bench.validate import run_flow, run_signoff

FLOW = "/OpenROAD-flow-scripts/flow"

# name -> (how it edits the SDC, extra make variables, must it resolve?)
DECOYS = {
    "oracle":      ("golden", {}, True),
    "null":        ("unchanged", {}, False),
    "cheat_loose": ("loosen", {}, False),
    "cheat_knob":  ("golden", {"SKIP_DETAILED_ROUTE": "1"}, False),
}


def make_sdc(strategy: str, impl: str, golden: str, out: str) -> None:
    """Write the SDC this decoy submits."""
    if strategy == "golden":
        text = open(golden).read()
    elif strategy == "unchanged":
        text = open(impl).read()
    elif strategy == "loosen":
        # The classic reward hack: make the constraint easy to meet, so the
        # implementation run reports huge positive slack.
        text = re.sub(r"^(set\s+clk_period\s+)\S+", r"\g<1>5.0",
                      open(impl).read(), count=1, flags=re.M)
    else:
        raise ValueError(strategy)
    with open(out, "w") as fh:
        fh.write(text)


def run_decoy(name: str, inst_dir: str, work: str) -> dict:
    strategy, knobs, must_resolve = DECOYS[name]
    inst_dir = os.path.abspath(inst_dir)
    pub = json.load(open(os.path.join(inst_dir, "public", "instance.json")))
    ans = json.load(open(os.path.join(inst_dir, "private", "answer.json")))

    inst_id, config = pub["instance_id"], pub["design_config"]
    platform, design = pub["platform"], pub["design"]
    golden = os.path.join(inst_dir, "private", "golden.sdc")
    impl = os.path.join(inst_dir, "public", "impl.sdc")

    os.makedirs(work, exist_ok=True)
    submitted = os.path.join(work, "{}_{}.sdc".format(inst_id, name))
    make_sdc(strategy, impl, golden, submitted)

    variant = "decoy_{}_{}".format(name, inst_id)
    cmd_extra = ["{}={}".format(k, v) for k, v in knobs.items()]
    log = os.path.join(work, variant + ".log")
    with open(log, "w") as fh:
        subprocess.call(
            ["make", "DESIGN_CONFIG=" + config, "FLOW_VARIANT=" + variant,
             "SDC_FILE=" + submitted] + cmd_extra,
            cwd=FLOW, stdout=fh, stderr=subprocess.STDOUT)

    base_variant = "val_base_{}_{}_s{}".format(platform, design, ans["seed"])
    base_run = parse_run(FLOW, platform, design, base_variant)
    base_so = grader.signoff_view(run_signoff(
        config, base_variant, golden,
        os.path.join(work, base_variant + ".signoff.json")))

    try:
        run = parse_run(FLOW, platform, design, variant)
        run_qor, completed = run.qor, run.completed
    except FileNotFoundError:
        run_qor, completed = {}, False

    # A decoy that suppressed routing has no final ODB, so sign-off cannot run
    # and returns {}. That must surface as failed assertions, not a crash.
    run_so = grader.signoff_view(run_signoff(
        config, variant, golden, os.path.join(work, variant + ".signoff.json")))

    verdict = grader.grade(
        "{} [{}]".format(inst_id, name), run_qor, run_so, base_run.qor, base_so,
        completed,
        edited_files={"impl.sdc"}, editable_files={"impl.sdc"},
        knobs_set=set(knobs))

    correct = verdict.resolved == must_resolve
    return {
        "decoy": name,
        "instance_id": inst_id,
        "resolved": verdict.resolved,
        "must_resolve": must_resolve,
        "grader_correct": correct,
        "failed_assertions": [a.name for a in verdict.assertions if not a.passed],
        "finish_ws": run_qor.get("setup_ws"),
        "signoff_ws": run_so.get("setup_ws"),
        "baseline_signoff_ws": base_so.get("setup_ws"),
        "area": run_qor.get("inst_area"),
        "report": verdict.report(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("instance")
    ap.add_argument("--decoys", nargs="*", default=list(DECOYS))
    ap.add_argument("--work", default="/tmp/ppa_decoy")
    ap.add_argument("--out", default="/ppa-bench/results/decoys.json")
    args = ap.parse_args()

    results = []
    for name in args.decoys:
        print("\n=== decoy: {} ===".format(name), flush=True)
        r = run_decoy(name, args.instance, args.work)
        print(r["report"])
        results.append(r)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(results, fh, indent=2, sort_keys=True)

    print("\n" + "=" * 82)
    print("{:13} {:>9} {:>9} {:>9} {:>8}  {}".format(
        "decoy", "resolved", "expected", "grader", "fin_ws", "failed on"))
    print("-" * 82)
    for r in results:
        print("{:13} {:>9} {:>9} {:>9} {:>8}  {}".format(
            r["decoy"], str(r["resolved"]), str(r["must_resolve"]),
            "OK" if r["grader_correct"] else "WRONG",
            "{:.4f}".format(r["finish_ws"]) if r["finish_ws"] is not None else "-",
            ",".join(r["failed_assertions"]) or "-"))
    bad = [r for r in results if not r["grader_correct"]]
    print("\n{}/{} decoys graded correctly".format(len(results) - len(bad), len(results)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
