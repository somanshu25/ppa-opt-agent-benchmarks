#!/usr/bin/env bash
# Run sign-off STA on a completed ORFS run using a held-out golden SDC.
#
#   signoff.sh <design_config> <flow_variant> <golden_sdc> <out_json>
#
# Sources the resolved ORFS environment via "make vars" rather than
# re-deriving it, so the sign-off run sees exactly the platform setup
# (liberty, corners, derate) that the flow itself used.
set -euo pipefail

DESIGN_CONFIG=${1:?design config}
FLOW_VARIANT=${2:?flow variant}
GOLDEN_SDC=${3:?golden sdc}
OUT_JSON=${4:?output json}

FLOW_DIR=${FLOW_DIR:-/OpenROAD-flow-scripts/flow}
BENCH_TCL=${BENCH_TCL:-/ppa-bench/tcl/signoff_sta.tcl}

cd "$FLOW_DIR"

# Materialise the resolved variable set for this design+variant.
make DESIGN_CONFIG="$DESIGN_CONFIG" FLOW_VARIANT="$FLOW_VARIANT" vars >/dev/null

PLATFORM=$(make DESIGN_CONFIG="$DESIGN_CONFIG" print-PLATFORM | awk '{print $2}')
NICK=$(make DESIGN_CONFIG="$DESIGN_CONFIG" print-DESIGN_NICKNAME | awk '{print $2}')
if [ -z "$NICK" ]; then
  NICK=$(make DESIGN_CONFIG="$DESIGN_CONFIG" print-DESIGN_NAME | awk '{print $2}')
fi

OBJ="objects/$PLATFORM/$NICK/$FLOW_VARIANT"
RES="results/$PLATFORM/$NICK/$FLOW_VARIANT"

# shellcheck disable=SC1091
source "$OBJ/vars.sh"

export SIGNOFF_ODB="$PWD/$RES/6_final.odb"
export SIGNOFF_SPEF="$PWD/$RES/6_final.spef"
export GOLDEN_SDC

if [ ! -f "$SIGNOFF_ODB" ]; then
  echo "signoff: no final ODB at $SIGNOFF_ODB (flow did not complete)" >&2
  exit 2
fi

# vars.sh deliberately excludes *_EXE/*_CMD/PATH entries, so resolve the
# binary from the flow rather than relying on it being on PATH.
OPENROAD_EXE=$(make DESIGN_CONFIG="$DESIGN_CONFIG" print-OPENROAD_EXE | awk '{print $2}')

mkdir -p "$(dirname "$OUT_JSON")"
"$OPENROAD_EXE" -exit -no_init -no_splash "$BENCH_TCL" -metrics "$OUT_JSON"
echo "signoff metrics -> $OUT_JSON"
