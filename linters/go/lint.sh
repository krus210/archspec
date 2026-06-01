#!/usr/bin/env bash
# archspec Go linter dispatcher. Contract:
#   lint.sh --list              -> prints supported subcommand names, one per line
#   lint.sh <sub> [args...]     -> runs `go run` for the linter, forwarding args
# Other languages should ship `linters/<lang>/lint.sh` with the same contract.
set -euo pipefail
LINTER_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ "${1:-}" == "--list" ]]; then
  echo "handler-idempotency"
  echo "outbox-pattern"
  echo "optimistic-locking"
  echo "swallowed-errors"
  exit 0
fi
# `go run` requires being inside the module dir. Resolve any relative
# --service-map / --code paths against the caller's cwd before chdir.
CALLER_PWD="$PWD"
args=()
while (($#)); do
  case "$1" in
    --service-map=*|--code=*)
      key="${1%%=*}"
      val="${1#*=}"
      [[ "$val" != /* ]] && val="$CALLER_PWD/$val"
      args+=("$key=$val")
      shift
      ;;
    --service-map|--code)
      key="$1"
      shift
      val="${1:-}"
      [[ -n "$val" && "$val" != /* ]] && val="$CALLER_PWD/$val"
      args+=("$key" "$val")
      shift
      ;;
    *)
      args+=("$1")
      shift
      ;;
  esac
done
cd "$LINTER_DIR"
exec go run . "${args[@]}"
