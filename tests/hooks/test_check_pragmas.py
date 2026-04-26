import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "hooks" / "pre-commit"))
from checks.check_pragmas import run as check_pragmas  # noqa: E402


def test_pragma_without_double_dash_blocks(stage_file, git_repo):
    stage_file("internal/x.go", "// archspec:ignore AI-001 missing dash explanation\nfunc f() {}\n")
    findings = check_pragmas(["internal/x.go"], cwd=git_repo)
    assert any(f.rule == "DET-015" and f.severity == "BLOCK" for f in findings)


def test_pragma_with_double_dash_passes(stage_file, git_repo):
    stage_file("internal/x.go", "// archspec:ignore AI-001 -- legacy adapter\nfunc f() {}\n")
    findings = check_pragmas(["internal/x.go"], cwd=git_repo)
    assert findings == []


def test_no_pragma_passes(stage_file, git_repo):
    stage_file("internal/x.go", "func f() {}\n")
    assert check_pragmas(["internal/x.go"], cwd=git_repo) == []
