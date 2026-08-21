# Sign-off STA against a held-out golden SDC.
#
# This is the anti-cheat core of the benchmark. The agent may edit the
# implementation SDC freely -- that is the task -- but it is graded by
# re-timing the physical design it produced against constraints it never saw.
# Loosening a constraint therefore cannot buy score: the loosened SDC is not
# the one used for judging.
#
# Mirrors scripts/open.tcl for the load sequence, then re-uses ORFS's own
# report_metrics so the emitted numbers are directly comparable to the
# flow's finish__* metrics (here prefixed signoff__*).
#
# Required env: SIGNOFF_ODB, GOLDEN_SDC   Optional: SIGNOFF_SPEF

utl::set_metrics_stage "signoff__{}"

source $::env(SCRIPTS_DIR)/util.tcl

source_env_var_if_exists PLATFORM_TCL

# Liberty must be re-read: read_db restores the netlist and physical data but
# not the timing libraries.
source $::env(SCRIPTS_DIR)/read_liberty.tcl

log_cmd read_db $::env(SIGNOFF_ODB)

# Parasitics from the agent's own routed design. Without these, sign-off would
# time an unrouted approximation and the gate would be meaningless.
if { [env_var_exists_and_non_empty SIGNOFF_SPEF] } {
  if { [file exists $::env(SIGNOFF_SPEF)] } {
    log_cmd read_spef $::env(SIGNOFF_SPEF)
  } else {
    puts "WARNING: SIGNOFF_SPEF set but missing: $::env(SIGNOFF_SPEF)"
  }
}

# read_db does not restore SDC constraints, so this is the only constraint
# source in play -- the golden SDC, not whatever the agent wrote.
log_cmd read_sdc $::env(GOLDEN_SDC)

# The golden SDC is the pre-CTS source constraint, which declares ideal clocks.
# The design being signed off is post-CTS and has a real clock tree, so timing
# it with ideal clocks would understate skew and insertion delay. CTS itself
# adds set_propagated_clock to the in-flow SDC; do the same here so sign-off
# and the flow's own finish__* numbers are measured under identical conditions.
# (tests/selftest_signoff.py enforces that they agree exactly.)
log_cmd set_propagated_clock [all_clocks]

if { [file exists $::env(PLATFORM_DIR)/derate.tcl] } {
  source $::env(PLATFORM_DIR)/derate.tcl
}

source $::env(SCRIPTS_DIR)/report_metrics.tcl
report_metrics 6 "signoff"
