"""Flow-knob allowlist and submission handling for the optimisation benchmark.

In the repair benchmark the agent edits one file and the danger is that it
games the *metric*.  Here the agent sets flow variables, and the danger is
different in kind: some ORFS variables reach past the objective and disable the
measurement, or redirect the flow away from the thing being judged.

A denylist is not enough for that.  ``SKIP_DETAILED_ROUTE`` is easy to
enumerate, but ``SDC_FILE`` is the real hazard -- an agent allowed to set
arbitrary make variables can point the flow at constraints of its own choosing
and walk straight through the sign-off gate that the whole benchmark rests on.
So this module **allowlists**: anything not named here is rejected.

The allowlist is not invented.  ORFS ships ``autotuner.json`` per design
declaring the knobs and ranges its own tuner is permitted to explore, and that
is the sanctioned space.  Two categories of autotuner entry are deliberately
excluded:

``_SDC_*``   the SDC lever wearing a knob costume.  ``_SDC_CLK_PERIOD`` would
             let the agent relax the clock -- sign-off would catch it, but the
             cleaner answer is that v1 is a knob benchmark, so constraints are
             out of scope.
``_FR_*``    requires rewriting a platform Tcl file rather than setting a
             variable, which is a different capability than knob tuning.
"""

from __future__ import annotations

import json
import os

# Variables that switch off the measurements the gates depend on. Redundant
# with the allowlist, kept because a silently-disabled check is the failure
# mode with the worst consequences.
DENYLIST = {
    "SKIP_REPORT_METRICS",
    "SKIP_DETAILED_ROUTE",
    "SKIP_INCREMENTAL_REPAIR",
    "SKIP_LAST_GASP",
    "SKIP_CTS_REPAIR_TIMING",
    "GENERATE_ARTIFACTS_ON_FAILURE",
}

# Curated additions beyond autotuner.json: real floorplan/placement knobs that
# ORFS designs set themselves, with ranges kept wide enough to matter but
# inside what the flow can actually complete.
EXTRA_KNOBS = {
    "CORE_UTILIZATION": {"type": "int", "minmax": [30, 75]},
    "PLACE_DENSITY": {"type": "float", "minmax": [0.30, 0.95]},
}


class KnobError(ValueError):
    """Raised when a submission is outside the permitted space."""


def load_space(flow_dir: str, platform: str, design: str,
               include_extra: bool = True) -> dict:
    """Build the permitted knob space for a design.

    Reads ORFS's own ``autotuner.json`` so the space is upstream-sanctioned
    rather than something we made up, then drops the pseudo-knobs.
    """
    path = os.path.join(flow_dir, "designs", platform, design, "autotuner.json")
    space: dict = {}
    if os.path.isfile(path):
        with open(path) as fh:
            raw = json.load(fh)
        for name, spec in raw.items():
            # Pseudo-knobs (see module docstring) and scalar path entries.
            if name.startswith("_") or not isinstance(spec, dict):
                continue
            if "minmax" not in spec:
                continue
            space[name] = {"type": spec.get("type", "float"),
                           "minmax": spec["minmax"],
                           "source": "autotuner.json"}
    if include_extra:
        for name, spec in EXTRA_KNOBS.items():
            space.setdefault(name, dict(spec, source="curated"))
    return space


def validate(submission: dict, space: dict) -> list[str]:
    """Check a knob submission against the permitted space.

    Returns a list of violations; empty means acceptable.  Every rejection
    reason is reported rather than just the first, so an agent (or a human
    reading the verdict) sees the whole problem at once.
    """
    problems = []
    for name, value in submission.items():
        if name in DENYLIST:
            problems.append("{} is denylisted (disables a graded check)".format(name))
            continue
        if name not in space:
            problems.append("{} is not in the permitted knob space".format(name))
            continue

        spec = space[name]
        try:
            num = float(value)
        except (TypeError, ValueError):
            problems.append("{} = {!r} is not numeric".format(name, value))
            continue
        if spec["type"] == "int" and float(num).is_integer() is False:
            problems.append("{} = {} must be an integer".format(name, value))
            continue
        lo, hi = spec["minmax"]
        if not (lo <= num <= hi):
            problems.append("{} = {} is outside [{}, {}]".format(name, value, lo, hi))
    return problems


def to_make_args(submission: dict, space: dict) -> list[str]:
    """Render a validated submission as make VAR=VALUE arguments."""
    args = []
    for name, value in sorted(submission.items()):
        if space.get(name, {}).get("type") == "int":
            args.append("{}={}".format(name, int(float(value))))
        else:
            args.append("{}={}".format(name, value))
    return args


def load_submission(path: str) -> dict:
    """Read an agent's knobs.json.

    A missing or unparseable submission is an empty knob set, i.e. "run the
    default config" -- which is exactly the null agent, and must not resolve.
    Treating it as an error instead would let a crashed agent be scored
    differently from a lazy one.
    """
    if not os.path.isfile(path):
        return {}
    try:
        with open(path) as fh:
            data = json.load(fh)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def describe(space: dict) -> str:
    """Human-readable knob space, for embedding in the task prompt."""
    lines = []
    for name in sorted(space):
        spec = space[name]
        lo, hi = spec["minmax"]
        lines.append("  {:38} {:5}  [{}, {}]".format(name, spec["type"], lo, hi))
    return "\n".join(lines)
