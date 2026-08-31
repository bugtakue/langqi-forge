#!/bin/sh
# Local packaging helper only. It never logs in, uploads, starts a run, or submits a project.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUTPUT=${2:-"$ROOT/dist/langqi-forge-agent.zip"}

case "${1:-pack}" in
  pack)
    exec "${PYTHON:-python3}" -m factory26_harness.submission_bundle \
      --source-root "$ROOT" \
      --output "$OUTPUT"
    ;;
  *)
    echo "Usage: sh arc.sh pack [output.zip]" >&2
    echo "This helper deliberately has no upload or submit command." >&2
    exit 2
    ;;
esac
