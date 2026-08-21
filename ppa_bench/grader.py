"""Grading: SWE-bench-shaped assertions over PPA metrics.

Two assertion sets, exactly as SWE-bench splits them:

* **PASS_TO_PASS** -- invariants that hold on the baseline and must still hold.
  These stop "fix one metric by wrecking another".  Alone they are satisfied by
  doing nothing at all.
* **FAIL_TO_PASS** -- the assertions the injected defect breaks.  These prove
  the defect was actually repaired.  Alone they are satisfied by any
  destructive shortcut that happens to move the target metric.

A run resolves only if *both* sets pass.  The QoR score is reported separately
and never blended into the verdict -- blending is precisely what would let an
agent buy its way past a failed gate.

The critical detail is *which numbers* the assertions read.  Every FAIL_TO_PASS
assertion is computed from ``signoff__*`` -- the agent's layout re-timed
against a golden SDC it never saw -- never from ``finish__*``.  For the silent
defect classes those two disagree in opposite directions: deleting
``set_input_delay`` makes the flow's own reported slack *improve* while the
design gets worse.  Reading ``finish__*`` would reward exactly the behaviour
this benchmark exists to catch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict

# ORFS variables that switch off the very measurements the gates depend on.
# An agent tuning flow knobs could set any of these and produce a run that
# looks flawless because nothing was checked. Absence of evidence must fail.
KNOB_DENYLIST = {
    "SKIP_REPORT_METRICS",     # report_metrics.tcl returns immediately
    "SKIP_DETAILED_ROUTE",     # skips routing, extraction and SPEF -> no DRC
    "SKIP_INCREMENTAL_REPAIR",
    "SKIP_LAST_GASP",
    "SKIP_CTS_REPAIR_TIMING",
    "GENERATE_ARTIFACTS_ON_FAILURE",
}


@dataclass
class Assertion:
    name: str
    kind: str            # "P2P" or "F2P"
    passed: bool
    detail: str

    def line(self) -> str:
        return "  [{}] {:28} {:4}  {}".format(
            "PASS" if self.passed else "FAIL", self.name, self.kind, self.detail)


@dataclass
class Verdict:
    instance_id: str
    resolved: bool
    assertions: list = field(default_factory=list)
    score: dict = field(default_factory=dict)

    def report(self) -> str:
        head = "{}: {}".format(self.instance_id,
                               "RESOLVED" if self.resolved else "NOT RESOLVED")
        body = "\n".join(a.line() for a in self.assertions)
        if self.score:
            body += "\n  score: " + json.dumps(self.score, sort_keys=True)
        return head + "\n" + body

    def to_dict(self) -> dict:
        return asdict(self)


def _cmp(name, kind, ok, got, want, how):
    return Assertion(name, kind, bool(ok),
                     "{} = {} (want {} {})".format(name, _fmt(got), how, _fmt(want)))


def _fmt(v):
    if isinstance(v, float):
        return "{:.6g}".format(v)
    return str(v)


def grade(instance_id: str,
          run_qor: dict,
          run_signoff: dict,
          baseline_qor: dict,
          baseline_signoff: dict,
          completed: bool,
          tolerance: float = 0.0,
          area_slack: float = 1.05,
          edited_files: set | None = None,
          editable_files: set | None = None,
          knobs_set: set | None = None) -> Verdict:
    """Evaluate one run against a baseline.

    ``tolerance`` is in nanoseconds and defaults to 0. Zero is defensible here
    because ORFS QoR is bit-exact deterministic across repeat runs
    (docs/FINDINGS.md F1), so the grader's independent re-run reproduces the
    agent's own run exactly -- there is no noise to absorb. It is left
    configurable because a *differently spelled* fix produces a genuinely
    different layout, and the semantic-null perturbation probe is what sets
    the right value there.
    """
    a: list[Assertion] = []

    # ---- PASS_TO_PASS: baseline invariants -------------------------------
    a.append(Assertion("flow_completed", "P2P", completed,
                       "flow reached 6_report" if completed else "flow did not finish"))
    a.append(_cmp("flow_errors", "P2P", run_qor.get("errors") == 0,
                  run_qor.get("errors"), 0, "=="))
    a.append(_cmp("drc_errors", "P2P", run_qor.get("drc_errors") == 0,
                  run_qor.get("drc_errors"), 0, "=="))
    a.append(_cmp("antenna_violations", "P2P", run_qor.get("antenna_viol") == 0,
                  run_qor.get("antenna_viol"), 0, "=="))
    a.append(_cmp("placement_violations", "P2P", run_qor.get("dpl_violations") == 0,
                  run_qor.get("dpl_violations"), 0, "=="))

    # Hold time is a P2P, not an F2P: none of our defect classes target it, so
    # it must simply survive whatever the agent did.
    base_hold = baseline_signoff.get("hold_ws")
    run_hold = run_signoff.get("hold_ws")
    if base_hold is not None and run_hold is not None:
        a.append(_cmp("signoff_hold_ws", "P2P", run_hold >= base_hold - tolerance,
                      run_hold, base_hold - tolerance, ">="))

    # Area is capped rather than fixed: a repair may legitimately shift it a
    # little, but a defect that "passes" by ballooning the design must not.
    base_area = baseline_qor.get("inst_area")
    run_area = run_qor.get("inst_area")
    if base_area and run_area:
        a.append(_cmp("area_not_ballooned", "P2P", run_area <= base_area * area_slack,
                      run_area, base_area * area_slack, "<="))

    if editable_files is not None and edited_files is not None:
        stray = edited_files - editable_files
        a.append(Assertion("edits_confined", "P2P", not stray,
                           "edited {} (allowed {})".format(
                               sorted(edited_files) or "nothing",
                               sorted(editable_files))))

    if knobs_set is not None:
        banned = knobs_set & KNOB_DENYLIST
        a.append(Assertion("no_disabled_checks", "P2P", not banned,
                           "denylisted knobs set: {}".format(sorted(banned))
                           if banned else "none set"))

    # ---- FAIL_TO_PASS: computed only from held-out sign-off --------------
    # Never from run_qor / finish__* -- see module docstring.
    for key, label in (("setup_ws", "signoff_setup_ws"),
                       ("setup_tns", "signoff_setup_tns")):
        base = baseline_signoff.get(key)
        got = run_signoff.get(key)
        if base is None or got is None:
            a.append(Assertion(label, "F2P", False, "missing sign-off metric"))
            continue
        a.append(_cmp(label, "F2P", got >= base - tolerance, got, base - tolerance, ">="))

    resolved = all(x.passed for x in a)

    score = {}
    if base_area and run_area:
        score["area_delta_pct"] = round(100.0 * (run_area - base_area) / base_area, 3)
    bp, rp = baseline_qor.get("power_total"), run_qor.get("power_total")
    if bp and rp:
        score["power_delta_pct"] = round(100.0 * (rp - bp) / bp, 3)

    return Verdict(instance_id=instance_id, resolved=resolved, assertions=a, score=score)


def signoff_view(signoff_metrics: dict) -> dict:
    """Project raw ``signoff__*`` metrics onto the short names grade() expects."""
    return {
        "setup_ws":  signoff_metrics.get("signoff__timing__setup__ws"),
        "setup_tns": signoff_metrics.get("signoff__timing__setup__tns"),
        "hold_ws":   signoff_metrics.get("signoff__timing__hold__ws"),
        "hold_tns":  signoff_metrics.get("signoff__timing__hold__tns"),
        "fmax":      signoff_metrics.get("signoff__timing__fmax"),
    }
