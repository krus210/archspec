"""DET-004 / DET-005 drift detection.

Re-runs the architecture-sync generators on the HEAD copy of SERVICE_MAP.yaml and
compares the regenerated outputs byte-for-byte to the HEAD copy of the diagrams
and ARCHITECTURE.md. Mismatches mean the user either edited the generated
artefacts by hand (DET-005) or forgot /archspec:sync after editing the YAML
(DET-004). Working-tree state is intentionally ignored so unrelated uncommitted
edits never block a push of otherwise clean commits.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    file: str
    line: int
    contract_ref: str
    message: str
    suggested_fix: str = ""


_GENERATED_OUTPUTS = (
    Path("docs/diagrams/context.mmd"),
    Path("docs/diagrams/container.mmd"),
    Path("docs/diagrams/sequence.mmd"),
    Path("docs/ARCHITECTURE.md"),
)


def _ensure_sync_on_path(repo_root: Path) -> None:
    sync_scripts = repo_root / "skills" / "architecture-sync" / "scripts"
    if str(sync_scripts) not in sys.path:
        sys.path.insert(0, str(sync_scripts))


def _head_blob(repo_root: Path, relative: str) -> bytes | None:
    # Pre-push must validate the bytes that will actually land on the remote,
    # i.e. HEAD — not the working tree, which may carry unrelated local edits.
    r = subprocess.run(
        ["git", "show", f"HEAD:{relative}"],
        cwd=repo_root, capture_output=True,
    )
    return r.stdout if r.returncode == 0 else None


def _regenerate(yaml_path: Path, output_dir: Path) -> dict[str, Path]:
    """Run sync.sync(yaml, output_dir), return {filename: regenerated_path}."""
    from sync import sync  # Plan 02

    output_dir.mkdir(parents=True, exist_ok=True)
    sync(yaml_path, output_dir)
    out: dict[str, Path] = {}
    for mmd in (output_dir / "diagrams").glob("*.mmd"):
        out[mmd.name] = mmd
    arch = output_dir / "ARCHITECTURE.md"
    if arch.is_file():
        out["ARCHITECTURE.md"] = arch
    return out


def check_drift(*, repo_root: Path) -> list[Finding]:
    _ensure_sync_on_path(repo_root)

    yaml_relative = "docs/SERVICE_MAP.yaml"
    yaml_head = _head_blob(repo_root, yaml_relative)
    if yaml_head is None:
        return []

    findings: list[Finding] = []
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        yaml_path = td_path / "SERVICE_MAP.yaml"
        yaml_path.write_bytes(yaml_head)
        regen_dir = td_path / "regen"
        regenerated = _regenerate(yaml_path, regen_dir)
        for relative in _GENERATED_OUTPUTS:
            fresh = regenerated.get(relative.name)
            if fresh is None:
                continue
            committed_bytes = _head_blob(repo_root, str(relative))
            if committed_bytes is None:
                findings.append(Finding(
                    rule="DET-004", severity="BLOCK",
                    file=str(relative), line=0,
                    contract_ref=yaml_relative,
                    message=f"missing generated file {relative}; run /archspec:sync",
                    suggested_fix="run `/archspec:sync` and commit the result",
                ))
                continue
            fresh_bytes = fresh.read_bytes()
            if committed_bytes != fresh_bytes:
                rule = "DET-005" if _looks_hand_edited(committed_bytes, fresh_bytes) else "DET-004"
                findings.append(Finding(
                    rule=rule, severity="BLOCK",
                    file=str(relative), line=0,
                    contract_ref=yaml_relative,
                    message=f"{relative} drifted from generator output",
                    suggested_fix="run `/archspec:sync` and commit the result",
                ))
    return findings


def _looks_hand_edited(committed: bytes, fresh: bytes) -> bool:
    """Heuristic: committed has lines absent from generator output → likely hand-edited."""
    committed_lines = set(committed.decode("utf-8").splitlines())
    fresh_lines = set(fresh.decode("utf-8").splitlines())
    return bool(committed_lines - fresh_lines)


def main() -> int:
    repo_root = Path.cwd()
    findings = check_drift(repo_root=repo_root)
    blocking = [f for f in findings if f.severity == "BLOCK"]
    for f in findings:
        print(f"{f.severity} {f.rule} {f.file}: {f.message}", file=sys.stderr)
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
