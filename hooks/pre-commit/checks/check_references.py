"""DET-003: every test: and contract: path in SERVICE_MAP.yaml exists on disk."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _finding import Finding  # noqa: E402
from _git import staged_blob  # noqa: E402

_TEST_REF_RE = re.compile(r"^([^:]+)::")


def _ref_targets(repo_root: Path, yaml_path: str, ref: str) -> list[Path]:
    """Candidate filesystem paths for a SERVICE_MAP reference."""
    cleaned = _TEST_REF_RE.match(ref)
    rel = cleaned.group(1) if cleaned else ref.split("#", 1)[0]
    targets = [repo_root / rel]
    # Also try resolving relative to the service root (yaml's grandparent),
    # so examples nested under examples/<svc>/docs/SERVICE_MAP.yaml stay
    # portable: docs/SERVICE_MAP.yaml referencing api/openapi.yaml resolves
    # against examples/<svc>/.
    yaml_parents = Path(yaml_path).parents
    if len(yaml_parents) >= 2:
        targets.append(repo_root / yaml_parents[1] / rel)
    return targets


def _exists(targets: list[Path]) -> bool:
    return any(t.exists() for t in targets)


def run(staged: list[str], cwd: Path | None = None) -> list[Finding]:
    repo = Path(cwd) if cwd else Path.cwd()
    findings: list[Finding] = []
    for path in (s for s in staged if s.endswith("SERVICE_MAP.yaml")):
        try:
            doc = yaml.safe_load(staged_blob(path, cwd=cwd))
        except yaml.YAMLError:
            continue
        if not doc:
            continue
        for ep in (doc.get("api") or {}).get("endpoints", []) or []:
            ref = ep.get("contract")
            if ref and not _exists(_ref_targets(repo, path, ref)):
                findings.append(
                    Finding("DET-003", "BLOCK", f"contract path missing: {ref}", file=path)
                )
        for ec in doc.get("edge_cases") or []:
            ref = ec.get("test")
            if ref and not _exists(_ref_targets(repo, path, ref)):
                findings.append(
                    Finding("DET-003", "BLOCK", f"edge_case test missing: {ref}", file=path)
                )
        for sc in doc.get("scenarios") or []:
            ref = sc.get("test")
            if ref and not _exists(_ref_targets(repo, path, ref)):
                findings.append(
                    Finding("DET-003", "BLOCK", f"scenario test missing: {ref}", file=path)
                )
    return findings
