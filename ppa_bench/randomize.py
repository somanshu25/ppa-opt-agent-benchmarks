"""Randomised golden constraints.

The golden SDC for an injected instance is, by default, upstream's own
``constraint.sdc``.  That is a problem: the answer is recoverable from the
environment (pristine file, git history, stale ``6_final.sdc``) *and*
plausibly from model training data, since ORFS is public.  Sanitising the
environment can never be proven complete.

Randomising the golden removes the answer instead of hiding it.  An instance
whose parameters were drawn at generation time cannot have been memorised,
and every leaked copy of upstream's value is simply wrong.

The sampled parameters are constrained, not arbitrary:

* ``clk_period`` is drawn from a range that has been *measured* to give a
  clean baseline for the design.  Sampling blind would reproduce the
  sky130hd/gcd failure mode -- a baseline that already violates timing, which
  destroys the FAIL-to-PASS substrate (see docs/FINDINGS.md F2).
* every generated instance must still pass ``BASELINE_PASS`` before it ships.
  Randomisation feeds the validation loop; it does not bypass it.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import re
from dataclasses import dataclass

# Kept outside the instances tree so it is never copied into an agent container.
SECRET_PATH = os.environ.get("PPA_BENCH_SECRET", "/ppa-bench/.sampling_secret")


@dataclass(frozen=True)
class GoldenParams:
    """The sampled constraint parameters that define one instance's golden."""

    clk_period: float
    clk_io_pct: float
    seed: int

    def describe(self) -> str:
        return "period={:.3f} io_pct={:.3f} seed={}".format(
            self.clk_period, self.clk_io_pct, self.seed)


# Per-design sampling ranges.
#
# clk_period bounds come from measurement, not from autotuner.json.
# autotuner declares 0.3-1.0 for gcd, but the lower half of that range does
# not close: upstream's own 0.46 leaves only +0.016 ns of slack. The lower
# bound here is the tightest period measured to give a clean baseline; the
# upper bound is capped so the design stays constrained enough for an injected
# defect to actually bite (too much slack makes instances vacuous).
PERIOD_RANGE = {
    ("nangate45", "gcd"): (0.50, 0.70),
    # aes does not close at its own upstream period. Measured: 0.82 (upstream)
    # gives WS -0.010, 0.85 gives -0.012, 0.90 gives -0.004; the first clean
    # baseline is 0.95 (+0.049, TNS 0) and 1.00 is cleaner still (+0.081).
    # An earlier guess of (0.85, 1.10) would have generated violating baselines
    # for most seeds -- the sky130hd/gcd failure mode (F2) all over again.
    # Both endpoints below are verified-clean measurements, not estimates.
    ("nangate45", "aes"): (0.95, 1.00),
}

# I/O budget as a fraction of the period. Upstream uses 0.2 everywhere.
IO_PCT_RANGE = (0.15, 0.30)

# Quantisation keeps generated SDCs readable and diffable.
PERIOD_STEP = 0.01
IO_PCT_STEP = 0.01


def _unit_draw(seed: int, field: str, secret: str) -> float:
    """Deterministic float in [0, 1) from (secret, seed, field).

    Uses a hash rather than ``random`` so an instance always reproduces the
    same parameters regardless of Python version or call order.

    ``secret`` is what makes the draw unrecoverable.  The seed appears in the
    public instance id and this sampler ships with the benchmark, so without a
    secret an agent recomputes the golden in one line -- the randomisation
    would defend against copying upstream while leaking the answer by a new
    route.  The secret lives outside the agent-visible tree.
    """
    digest = hashlib.sha256(
        "{}:{}:{}".format(secret, seed, field).encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def load_secret(path: str = SECRET_PATH) -> str:
    """Read the sampling secret, creating one on first use."""
    if not os.path.isfile(path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as fh:
            fh.write(secrets.token_hex(32))
        os.chmod(path, 0o600)
    return open(path).read().strip()


def _draw_quantised(seed, field, secret, lo, hi, step) -> float:
    """Draw a value from [lo, hi] on a `step` grid, deterministically."""
    steps = int(round((hi - lo) / step))
    idx = min(int(_unit_draw(seed, field, secret) * (steps + 1)), steps)
    return round(lo + idx * step, 4)


def sample_params(platform: str, design: str, seed: int,
                  secret: str | None = None) -> GoldenParams:
    """Draw golden constraint parameters for one instance.

    ``secret`` defaults to the on-disk sampling secret. Pass it explicitly only
    to reproduce a previously generated instance.
    """
    if (platform, design) not in PERIOD_RANGE:
        raise KeyError(
            "no measured period range for {}/{} -- run the sweep before "
            "randomising this design".format(platform, design))
    if secret is None:
        secret = load_secret()

    lo, hi = PERIOD_RANGE[(platform, design)]
    io_lo, io_hi = IO_PCT_RANGE
    return GoldenParams(
        clk_period=_draw_quantised(seed, "period", secret, lo, hi, PERIOD_STEP),
        clk_io_pct=_draw_quantised(seed, "io_pct", secret, io_lo, io_hi, IO_PCT_STEP),
        seed=seed,
    )


def render_golden(template_sdc: str, params: GoldenParams) -> str:
    """Rewrite a template SDC to use the sampled parameters.

    Only the two scalar assignments change; the rest of the file -- including
    the ``[expr $clk_period * $clk_io_pct]`` forms that derive from them -- is
    left byte-identical to upstream, so the instance stays a faithful ORFS
    design rather than a synthetic one.

    The values are written as bare literals on purpose: ORFS scrapes the period
    out of this file with a regex and feeds it to ABC, and an ``[expr ...]``
    form silently defeats that scrape (docs/FINDINGS.md F5).
    """
    out, n_period = re.subn(
        r"^(set\s+clk_period\s+)\S+",
        lambda m: m.group(1) + "{:g}".format(params.clk_period),
        template_sdc, count=1, flags=re.M)
    out, n_pct = re.subn(
        r"^(set\s+clk_io_pct\s+)\S+",
        lambda m: m.group(1) + "{:g}".format(params.clk_io_pct),
        out, count=1, flags=re.M)

    if not n_period:
        raise ValueError("template has no 'set clk_period' line to randomise")
    if not n_pct:
        raise ValueError("template has no 'set clk_io_pct' line to randomise")
    return out
