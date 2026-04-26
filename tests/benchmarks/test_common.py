from benchmarks._common import repo_root, results_dir, write_json_report


def test_repo_root_returns_path_with_benchmarks_dir():
    root = repo_root()
    assert (root / "benchmarks").is_dir()


def test_results_dir_creates_and_returns_path(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHSPEC_BENCHMARK_RESULTS", str(tmp_path / "out"))
    rd = results_dir()
    assert rd.is_dir()
    assert rd == tmp_path / "out"


def test_write_json_report_atomic_and_sorted_keys(tmp_path):
    target = tmp_path / "report.json"
    write_json_report(target, {"b": 2, "a": 1})
    text = target.read_text(encoding="utf-8")
    assert text == '{\n  "a": 1,\n  "b": 2\n}\n'
