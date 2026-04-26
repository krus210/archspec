from benchmarks.determinism.run_determinism import run_determinism_suite


def test_determinism_minimal_input_passes(tmp_path):
    report = run_determinism_suite(results_path=tmp_path / "report.json", runs=3)
    assert report["status"] == "pass"
    assert report["runs_per_input"] == 3
    minimal = next(r for r in report["inputs"] if r["name"] == "01_minimal")
    assert minimal["status"] == "pass"
    assert all(len(set(h)) == 1 for h in minimal["per_output_hashes"].values())


def test_determinism_report_written_to_disk(tmp_path):
    target = tmp_path / "report.json"
    run_determinism_suite(results_path=target, runs=2)
    assert target.is_file()
    assert target.read_text(encoding="utf-8").endswith("\n")
