import shutil

import pytest

from benchmarks.violations.run_violations import run_violations_suite


@pytest.mark.skipif(shutil.which("go") is None, reason="go toolchain not installed")
def test_violations_suite_passes_with_seed_fixtures(tmp_path):
    report = run_violations_suite(results_path=tmp_path / "violations.json", threshold=0.95)
    assert report["fixture_count"] == 3, report
    assert report["status"] == "pass", report
    for fx in report["fixtures"]:
        assert fx["status"] == "pass", fx
        assert fx["metrics"]["f1"] >= 0.95, fx
