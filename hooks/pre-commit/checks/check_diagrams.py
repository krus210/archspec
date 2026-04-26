"""DET-004 (AUTO-FIX): YAML staged without regenerated diagrams.
DET-005 (BLOCK): .mmd staged but YAML untouched (= manual edit of generated artifact)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _finding import Finding  # noqa: E402

_DIAGRAM_FILES = ("context.mmd", "container.mmd", "sequence.mmd")
_SYNC = Path(__file__).resolve().parents[3] / "skills" / "architecture-sync" / "scripts" / "sync.py"


def _staged_yaml(staged: list[str]) -> str | None:
    yamls = [s for s in staged if s.endswith("SERVICE_MAP.yaml")]
    return yamls[0] if yamls else None


def _staged_diagrams(staged: list[str]) -> list[str]:
    return [s for s in staged if s.endswith(".mmd") and Path(s).name in _DIAGRAM_FILES]


def run(staged: list[str], cwd: Path | None = None) -> list[Finding]:
    findings: list[Finding] = []
    yaml_path = _staged_yaml(staged)
    diagrams = _staged_diagrams(staged)

    if not yaml_path and diagrams:
        for d in diagrams:
            findings.append(Finding(
                "DET-005", "BLOCK", "manual edit of generated diagram",
                file=d,
                fix_hint="edit SERVICE_MAP.yaml and rerun /archspec:sync",
            ))
        return findings

    if yaml_path:
        repo = Path(cwd) if cwd else Path.cwd()
        docs_dir = (repo / yaml_path).parent
        with tempfile.TemporaryDirectory() as tmp:
            try:
                subprocess.run(
                    [sys.executable, str(_SYNC), str(repo / yaml_path), tmp],
                    check=True, capture_output=True,
                )
            except subprocess.CalledProcessError:
                # sync.py failed (e.g. malformed YAML). DET-001 (check_schema)
                # owns error reporting for that; silently skip diagram checks.
                return []
            for fname in _DIAGRAM_FILES:
                expected = (Path(tmp) / "diagrams" / fname).read_bytes()
                actual_path = docs_dir / "diagrams" / fname
                actual = actual_path.read_bytes() if actual_path.exists() else b""
                if expected != actual:
                    findings.append(Finding(
                        "DET-004", "AUTO-FIX",
                        f"diagrams out of sync with SERVICE_MAP.yaml ({fname})",
                        file=str(actual_path.relative_to(repo)),
                        fix_hint="run /archspec:sync and stage the result",
                    ))
            expected_md = (Path(tmp) / "ARCHITECTURE.md").read_bytes()
            actual_md_path = docs_dir / "ARCHITECTURE.md"
            actual_md = actual_md_path.read_bytes() if actual_md_path.exists() else b""
            if expected_md != actual_md:
                findings.append(Finding(
                    "DET-004", "AUTO-FIX",
                    "ARCHITECTURE.md out of sync with SERVICE_MAP.yaml",
                    file=str(actual_md_path.relative_to(repo)),
                    fix_hint="run /archspec:sync and stage the result",
                ))
    return findings
