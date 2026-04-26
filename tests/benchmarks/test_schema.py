from benchmarks.schema.run_schema import run_schema_suite


def test_schema_suite_passes_when_all_fixtures_match(tmp_path):
    report = run_schema_suite(results_path=tmp_path / "schema.json")
    assert report["suite"] == "schema"
    assert report["status"] == "pass", report
    assert report["valid_count"] >= 2
    assert report["invalid_count"] >= 3


def test_schema_invalid_fixture_must_have_expected_json(tmp_path):
    report = run_schema_suite(results_path=tmp_path / "schema.json")
    for entry in report["invalid"]:
        assert entry["status"] == "pass", entry
        assert "expected_error_code" in entry
