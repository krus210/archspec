import json
import shutil
from pathlib import Path

import pytest

from benchmarks._record import record_fixture


@pytest.mark.skipif(shutil.which("go") is None, reason="go toolchain not installed")
def test_record_overwrites_expected_json_with_actual_findings(tmp_path):
    src = Path("benchmarks/violations/fixtures/01_missing_idempotency_key")
    dst = tmp_path / "01_missing_idempotency_key"
    shutil.copytree(src, dst)
    target = dst / "expected.json"
    target.write_text("[]\n", encoding="utf-8")
    record_fixture(dst)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert any(f["rule"] == "AI-001" for f in data)
