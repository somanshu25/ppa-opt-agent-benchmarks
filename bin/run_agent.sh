#!/usr/bin/env bash
# Run a headless baseline agent on one instance, in isolation.
#
#   run_agent.sh <instance_dir> <out_dir> [max_turns]
#
# The agent gets a throwaway container holding the real ORFS toolchain and the
# instance's public/ files -- nothing else. Isolation is enforced here, not by
# the image: this script strips every path that leaks the reference
# constraints before the agent starts.
#
# Leak paths removed (all found by auditing, see docs/FINDINGS.md):
#   .git                              git show HEAD:...constraint.sdc
#   flow/results, flow/logs           stale 6_final.sdc holds elaborated goldens
#   designs/<d>/rules-base.json       upstream's expected WS / area
#   designs/<d>/autotuner.json        declares the clock-period range
#   designs/<d>/constraint.sdc        pristine upstream SDC -> overwritten with impl.sdc
#
# Randomised goldens mean even a missed path yields the wrong value, but
# defence in depth is cheap here.
set -euo pipefail

# Git Bash on Windows rewrites bare absolute paths in argv into Windows paths,
# which turns container paths like /work into C:/Program Files/Git/work.
# Harmless on Linux; required here.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

INSTANCE=$(cd "${1:?instance dir}" && pwd)
OUT=${2:?output dir}
MAX_TURNS=${3:-40}

: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY must be set (not echoed)}"

NAME=$(basename "$INSTANCE")
CONTAINER="ppabench_agent_${NAME}"
IMAGE=${AGENT_IMAGE:-ppa-bench/orfs-agent:latest}

PLATFORM=$(python3 -c "import json;print(json.load(open('$INSTANCE/public/instance.json'))['platform'])" 2>/dev/null \
    || grep -oP '"platform":\s*"\K[^"]+' "$INSTANCE/public/instance.json")
DESIGN=$(grep -oP '"design":\s*"\K[^"]+' "$INSTANCE/public/instance.json")
CONFIG=$(grep -oP '"design_config":\s*"\K[^"]+' "$INSTANCE/public/instance.json")

mkdir -p "$OUT"

# With path conversion disabled, host-side arguments to `docker cp` must be
# translated explicitly. cygpath is a no-op outside Git Bash.
hostpath() { cygpath -m "$1" 2>/dev/null || echo "$1"; }
HINST=$(hostpath "$INSTANCE")
HOUT=$(hostpath "$(cd "$OUT" && pwd)")

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" "$IMAGE" sleep infinity >/dev/null

echo "[$NAME] sanitising workspace"
docker exec "$CONTAINER" bash -lc "
  set -e
  cd /OpenROAD-flow-scripts
  rm -rf .git flow/results flow/logs flow/objects
  rm -f flow/designs/$PLATFORM/$DESIGN/rules-base.json \
        flow/designs/$PLATFORM/$DESIGN/autotuner.json
  mkdir -p /work
"

# Stage only public/. private/ never enters this container.
docker cp "$HINST/public/impl.sdc"     "$CONTAINER:/work/impl.sdc"
docker cp "$HINST/public/instance.json" "$CONTAINER:/work/instance.json"
# The pristine design SDC is itself a leak; replace it with the defective one.
docker exec "$CONTAINER" cp /work/impl.sdc \
    "/OpenROAD-flow-scripts/flow/designs/$PLATFORM/$DESIGN/constraint.sdc"

# Audit what the agent could actually reach. Recorded as evidence either way.
echo "[$NAME] leak audit"
docker exec "$CONTAINER" bash -lc "
  grep -rlF 'set_input_delay' /OpenROAD-flow-scripts/flow/results 2>/dev/null | head -3
  ls /OpenROAD-flow-scripts/.git 2>/dev/null && echo 'GIT PRESENT'
  true
" | tee "$OUT/leak_audit.txt"

# Build instructions are given rather than left to be discovered: the task is
# constraint diagnosis, not ORFS command-line archaeology. Withholding them
# would add variance that has nothing to do with the skill being measured.
PROMPT="$(cat "$INSTANCE/public/prompt.md")

## Building the design

You have the full OpenROAD flow. Build and inspect QoR with:

    cd /OpenROAD-flow-scripts/flow
    make DESIGN_CONFIG=$CONFIG SDC_FILE=/work/impl.sdc FLOW_VARIANT=try1

Use a fresh FLOW_VARIANT name for each attempt. Metrics land in
logs/$PLATFORM/$DESIGN/<variant>/*.json -- 6_report.json has the final timing,
power and area. A run takes about 40 seconds.

## Deliverable

/work/impl.sdc is the ONLY thing collected. It is read exactly as you leave it,
whenever you stop -- including if you run out of turns mid-investigation.

So write your best answer so far to /work/impl.sdc **after every trial**, not
at the end. If a sweep shows one value is better than what is currently in the
file, write it immediately, then continue exploring. Never leave the file
holding a value you have already shown to be worse."

echo "$PROMPT" > "$OUT/prompt_sent.md"
docker cp "$HOUT/prompt_sent.md" "$CONTAINER:/work/prompt.md" >/dev/null

echo "[$NAME] running agent (max_turns=$MAX_TURNS)"
START=$(date +%s)
set +e
# IS_SANDBOX tells Claude Code it is already inside a disposable container, so
# --dangerously-skip-permissions is allowed as root. Unattended runs cannot
# answer permission prompts, and the container *is* the security boundary.
docker exec -e ANTHROPIC_API_KEY -e IS_SANDBOX=1 -w /work "$CONTAINER" \
    claude -p "$PROMPT" \
      --max-turns "$MAX_TURNS" \
      --dangerously-skip-permissions \
      --output-format stream-json --verbose \
    > "$OUT/transcript.jsonl" 2> "$OUT/agent_stderr.txt"
RC=$?
set -e
END=$(date +%s)
echo "[$NAME] agent exited rc=$RC after $((END-START))s"

docker cp "$CONTAINER:/work/impl.sdc" "$HOUT/impl_submitted.sdc"
docker rm -f "$CONTAINER" >/dev/null

{
  echo "instance=$NAME"
  echo "rc=$RC"
  echo "wall_seconds=$((END-START))"
} > "$OUT/agent_meta.txt"

echo "[$NAME] submitted SDC -> $OUT/impl_submitted.sdc"
