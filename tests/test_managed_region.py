from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from _common import (
    MANAGED_REGION_END,
    MANAGED_REGION_START,
    apply_managed_region,
)

ROOT = Path(__file__).resolve().parent.parent
SYNC = ROOT / "skills" / "architecture-sync" / "scripts" / "sync.py"
FULL = ROOT / "tests" / "fixtures" / "yaml" / "valid" / "full.yaml"


def _run_sync(docs: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SYNC), str(FULL), str(docs)],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )


def test_sync_preserves_user_prefix_and_suffix(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    arch = docs / "ARCHITECTURE.md"
    prefix = "## My notes\nSome user-authored prose.\n\n"
    suffix = "\n## More notes\nFurther user prose.\n"
    arch.write_text(
        f"{prefix}{MANAGED_REGION_START}\nold managed\n{MANAGED_REGION_END}{suffix}",
        encoding="utf-8",
    )

    r = _run_sync(docs)
    assert r.returncode == 0, r.stderr

    new_text = arch.read_text(encoding="utf-8")
    assert new_text.startswith(prefix), "user prefix was clobbered"
    assert new_text.endswith(suffix), "user suffix was clobbered"
    assert "old managed" not in new_text
    assert MANAGED_REGION_START in new_text
    assert MANAGED_REGION_END in new_text
    # Fresh content (e.g., service name from full.yaml) must appear inside.
    assert "# " in new_text  # rendered architecture heading


def test_sync_creates_full_file_when_target_missing(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    r = _run_sync(docs)
    assert r.returncode == 0, r.stderr
    text = (docs / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert text.startswith(MANAGED_REGION_START)
    assert MANAGED_REGION_END in text


def test_apply_managed_region_raises_on_unbalanced_markers(tmp_path):
    target = tmp_path / "ARCHITECTURE.md"
    target.write_text(
        f"## prefix\n{MANAGED_REGION_START}\nmissing end\n",
        encoding="utf-8",
    )
    fresh = f"{MANAGED_REGION_START}\nnew\n{MANAGED_REGION_END}\n"
    with pytest.raises(ValueError):
        apply_managed_region(target, fresh)


def test_apply_managed_region_returns_fresh_when_target_missing(tmp_path):
    target = tmp_path / "ARCHITECTURE.md"
    fresh = f"{MANAGED_REGION_START}\nbody\n{MANAGED_REGION_END}\n"
    assert apply_managed_region(target, fresh) == fresh


def test_apply_managed_region_returns_fresh_when_no_start_marker(tmp_path):
    target = tmp_path / "ARCHITECTURE.md"
    target.write_text("legacy file without markers\n", encoding="utf-8")
    fresh = f"{MANAGED_REGION_START}\nbody\n{MANAGED_REGION_END}\n"
    assert apply_managed_region(target, fresh) == fresh
