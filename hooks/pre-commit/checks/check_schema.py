"""DET-001: SERVICE_MAP.yaml conforms to JSON Schema."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _finding import Finding  # noqa: E402
from _git import staged_blob  # noqa: E402

SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "skills"
    / "architecture-sync"
    / "schema"
    / "servicemap.schema.json"
)


def run(staged: list[str], cwd: Path | None = None) -> list[Finding]:
    targets = [s for s in staged if s.endswith("SERVICE_MAP.yaml")]
    if not targets:
        return []
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft7Validator(schema)
    findings: list[Finding] = []
    for path in targets:
        try:
            doc = yaml.safe_load(staged_blob(path, cwd=cwd))
        except yaml.YAMLError as e:
            findings.append(Finding("DET-001", "BLOCK", f"YAML parse error: {e}", file=path))
            continue
        for err in validator.iter_errors(doc):
            loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
            findings.append(Finding("DET-001", "BLOCK", f"{loc}: {err.message}", file=path))
    return findings
