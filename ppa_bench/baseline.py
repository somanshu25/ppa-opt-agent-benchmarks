"""Frozen baselines.

Randomising the golden means the reference QoR is no longer upstream's -- it
has to be *measured*, once, by running the flow with the sampled golden SDC.

That run happens at instance-build time and is then frozen into
``private/baseline.json``.  Two reasons:

* **Grading must not re-derive it.** Otherwise every agent attempt pays for a
  baseline run it could have read from disk, and grading depends on a
  particular container's flow tree still holding the right variant.
* **Instances become portable.** With the baseline frozen, an instance
  directory is self-contained: clone the repo, run the agent, grade. Nothing
  has to be reproduced first.

Freezing is only sound because ORFS QoR is bit-exact deterministic
(docs/FINDINGS.md F1). A frozen number that drifted between machines would be
worse than no number at all, so ``verify_frozen`` re-checks it on demand.

The baseline is shared by every class at the same (design, seed), so validating
N classes costs 1 + N flow runs rather than 3N.
"""

from __future__ import annotations

import json
import os

BASELINE_FILE = "baseline.json"


class BaselineError(RuntimeError):
    pass


def baseline_variant(platform: str, design: str, seed: int) -> str:
    """Flow variant name for a (design, seed) baseline."""
    return "val_base_{}_{}_s{}".format(platform, design, seed)


def freeze(inst_dir: str, qor: dict, signoff: dict, variant: str,
           params: dict, completed: bool) -> dict:
    """Write the measured baseline into the instance's private directory.

    Enforces the sign-off self-test as a precondition. For a baseline the
    golden SDC *is* the SDC the flow ran with, so sign-off must reproduce the
    flow's own timing exactly. If it does not, the sign-off path is
    misconfigured -- as it was when it timed ideal clocks against a post-CTS
    design -- and every downstream verdict would be quietly biased.
    """
    fin, sgn = qor.get("setup_ws"), signoff.get("setup_ws")
    if fin is None or sgn is None:
        raise BaselineError(
            "baseline is missing setup_ws (finish={}, signoff={}); the flow or "
            "the sign-off run did not complete".format(fin, sgn))
    if fin != sgn:
        raise BaselineError(
            "sign-off self-test FAILED on the baseline: finish setup_ws={} but "
            "signoff setup_ws={}. The sign-off path is measuring something the "
            "flow did not.".format(fin, sgn))

    record = {
        "variant": variant,
        "golden_params": params,
        "completed": completed,
        "qor": qor,
        "signoff": signoff,
        "selftest": {"finish_setup_ws": fin, "signoff_setup_ws": sgn, "exact": True},
    }
    path = os.path.join(inst_dir, "private", BASELINE_FILE)
    with open(path, "w") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
    return record


def load(inst_dir: str) -> dict | None:
    """Read the frozen baseline, or None if this instance has not been built."""
    path = os.path.join(inst_dir, "private", BASELINE_FILE)
    if not os.path.isfile(path):
        return None
    with open(path) as fh:
        return json.load(fh)


def verify_frozen(inst_dir: str, qor: dict, signoff: dict) -> list[str]:
    """Compare a fresh baseline measurement against the frozen one.

    Returns a list of drift descriptions; empty means the frozen baseline still
    reproduces. Determinism is an assumption the whole grader rests on, so it
    is worth being able to check rather than trust.
    """
    frozen = load(inst_dir)
    if frozen is None:
        return ["no frozen baseline to verify against"]

    drift = []
    for name, fresh_map, frozen_map in (("qor", qor, frozen["qor"]),
                                        ("signoff", signoff, frozen["signoff"])):
        for key, want in frozen_map.items():
            got = fresh_map.get(key)
            if got != want:
                drift.append("{}.{}: frozen={} fresh={}".format(name, key, want, got))
    return drift
