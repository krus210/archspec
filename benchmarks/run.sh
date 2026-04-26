#!/usr/bin/env bash
# benchmarks/run.sh — run all archspec benchmark suites and aggregate exit codes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="$REPO_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="python3"
fi

mode="all"
record_target=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --record)
            if [[ $# -lt 2 ]]; then
                echo "--record requires a fixture dir" >&2
                exit 2
            fi
            mode="record"
            record_target="$2"
            shift 2
            ;;
        --suite)
            if [[ $# -lt 2 ]]; then
                echo "--suite requires a name (determinism|schema|violations)" >&2
                exit 2
            fi
            mode="$2"
            shift 2
            ;;
        -h|--help)
            cat <<USAGE
Usage: ./benchmarks/run.sh [--suite determinism|schema|violations] [--record <fixture-dir>]
Default: run all three suites sequentially.
USAGE
            exit 0
            ;;
        *)
            echo "unknown arg: $1" >&2
            exit 2
            ;;
    esac
done

if [[ "$mode" == "record" ]]; then
    if [[ -z "$record_target" ]]; then
        echo "--record requires a fixture dir" >&2
        exit 2
    fi
    "$PYTHON" -m benchmarks._record "$record_target"
    exit 0
fi

mkdir -p benchmarks/results
overall=0

run_suite() {
    local name="$1"
    local module="$2"
    echo "=== $name ==="
    if ! "$PYTHON" -m "$module" --out "benchmarks/results/${name}.json"; then
        overall=1
    fi
}

case "$mode" in
    all)
        run_suite determinism benchmarks.determinism.run_determinism
        run_suite schema       benchmarks.schema.run_schema
        run_suite violations   benchmarks.violations.run_violations
        ;;
    determinism|schema|violations)
        run_suite "$mode" "benchmarks.${mode}.run_${mode}"
        ;;
    *)
        echo "unknown suite: $mode" >&2
        exit 2
        ;;
esac

"$PYTHON" - <<'PY'
import json, pathlib
results = pathlib.Path("benchmarks/results")
report = {}
for f in sorted(results.glob("*.json")):
    if f.name == "report.json":
        continue
    report[f.stem] = json.loads(f.read_text(encoding="utf-8"))
target = results / "report.json"
target.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"aggregate report: {target}")
PY

exit $overall
