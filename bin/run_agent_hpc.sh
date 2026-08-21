#!/usr/bin/env bash
# Run a headless agent on an HP-C optimisation instance.
#
#   run_agent_hpc.sh <instance_dir> <out_dir> [max_turns]
#
# Differs from run_agent.sh in three ways:
#   * the deliverable is knobs.json, not impl.sdc
#   * the design SDC is left pristine -- it is the sign-off reference and the
#     agent is not permitted to touch it
#   * flow runs are counted, because run budget is part of the problem here
set -euo pipefail

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

INSTANCE=$(cd "${1:?instance dir}" && pwd)
OUT=${2:?output dir}
MAX_TURNS=${3:-60}

: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY must be set (not echoed)}"

NAME=$(basename "$INSTANCE")
CONTAINER="ppabench_hpc_${NAME}"
IMAGE=${AGENT_IMAGE:-ppa-bench/orfs-agent:latest}

PLATFORM=$(grep -oP '"platform":\s*"\K[^"]+' "$INSTANCE/public/instance.json")
DESIGN=$(grep -oP '"design":\s*"\K[^"]+' "$INSTANCE/public/instance.json")

mkdir -p "$OUT"
hostpath() { cygpath -m "$1" 2>/dev/null || echo "$1"; }
HINST=$(hostpath "$INSTANCE")
HOUT=$(hostpath "$(cd "$OUT" && pwd)")

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" "$IMAGE" sleep infinity >/dev/null

# There is no hidden answer in HP-C, so sanitisation is lighter than for
# repair. rules-base.json still goes: it states upstream's expected area, which
# is a hint about the achievable target.
echo "[$NAME] preparing workspace"
docker exec "$CONTAINER" bash -lc "
  set -e
  rm -rf /OpenROAD-flow-scripts/flow/results /OpenROAD-flow-scripts/flow/logs
  rm -f /OpenROAD-flow-scripts/flow/designs/$PLATFORM/$DESIGN/rules-base.json
  mkdir -p /work
"

docker cp "$HINST/public/knobs.json"    "$CONTAINER:/work/knobs.json"
docker cp "$HINST/public/instance.json" "$CONTAINER:/work/instance.json"

PROMPT="$(cat "$INSTANCE/public/prompt.md")

## Running the flow

    cd /OpenROAD-flow-scripts/flow
    make DESIGN_CONFIG=./designs/$PLATFORM/$DESIGN/config.mk FLOW_VARIANT=try1 \\
         CORE_UTILIZATION=60 PLACE_DENSITY_LB_ADDON=0.1

Pass knobs as make variables, one fresh FLOW_VARIANT per trial. Metrics land in
logs/$PLATFORM/$DESIGN/<variant>/6_report.json; the objective is
\`finish__design__die__area\`. Baseline (default config) is a run with no knob
overrides -- measure it first if you want a reference."

echo "$PROMPT" > "$OUT/prompt_sent.md"

echo "[$NAME] running agent (max_turns=$MAX_TURNS)"
START=$(date +%s)
set +e
docker exec -e ANTHROPIC_API_KEY -e IS_SANDBOX=1 -w /work "$CONTAINER" \
    claude -p "$PROMPT" \
      --max-turns "$MAX_TURNS" \
      --dangerously-skip-permissions \
      --output-format stream-json --verbose \
    > "$OUT/transcript.jsonl" 2> "$OUT/agent_stderr.txt"
RC=$?
set -e
END=$(date +%s)

# Budget is measured from the agent's own container: one flow variant directory
# per trial it ran. Counted before the container is destroyed.
RUNS=$(docker exec "$CONTAINER" bash -lc \
    "ls /OpenROAD-flow-scripts/flow/logs/$PLATFORM/$DESIGN 2>/dev/null | wc -l" || echo 0)
docker exec "$CONTAINER" bash -lc \
    "ls /OpenROAD-flow-scripts/flow/logs/$PLATFORM/$DESIGN 2>/dev/null" \
    > "$OUT/flow_variants.txt" || true

echo "[$NAME] agent exited rc=$RC after $((END-START))s, $RUNS flow runs"

docker cp "$CONTAINER:/work/knobs.json" "$HOUT/knobs_submitted.json"
docker rm -f "$CONTAINER" >/dev/null

{
  echo "instance=$NAME"
  echo "rc=$RC"
  echo "wall_seconds=$((END-START))"
  echo "flow_runs=$RUNS"
} > "$OUT/agent_meta.txt"

echo "[$NAME] submitted -> $OUT/knobs_submitted.json"
cat "$OUT/knobs_submitted.json"
