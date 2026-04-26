"""DET-015: every `archspec:ignore` pragma must include a `-- <reason>` comment."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _finding import Finding  # noqa: E402
from _git import staged_blob  # noqa: E402

_PRAGMA_RE = re.compile(r"archspec:ignore(?:-block)?\s+([A-Z]+-\d+(?:\s+[A-Z]+-\d+)*)(.*)$")
_SOURCE_EXTS = (".go", ".py", ".js", ".ts", ".java", ".kt", ".rs")


def run(staged: list[str], cwd: Path | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for path in staged:
        if not path.endswith(_SOURCE_EXTS):
            continue
        try:
            text = staged_blob(path, cwd=cwd)
        except subprocess.CalledProcessError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            m = _PRAGMA_RE.search(line)
            if not m:
                continue
            tail = m.group(2)
            if "--" not in tail:
                findings.append(Finding(
                    "DET-015", "BLOCK",
                    "archspec:ignore pragma missing `-- <reason>` comment",
                    file=path, line=i,
                    fix_hint="use `// archspec:ignore AI-XXX -- short reason here`",
                ))
    return findings
