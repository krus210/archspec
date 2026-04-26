from benchmarks.violations.run_violations import compute_metrics


def _f(rule, file, line):
    return {"rule": rule, "file": file, "line": line}


def test_compute_metrics_perfect_match():
    expected = [_f("AI-001", "h.go", 10), _f("AI-002", "p.go", 22)]
    actual = [_f("AI-001", "h.go", 10), _f("AI-002", "p.go", 22)]
    m = compute_metrics(expected=expected, actual=actual)
    assert m == {"tp": 2, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0}


def test_compute_metrics_partial_match_returns_correct_f1():
    expected = [_f("AI-001", "a.go", 1), _f("AI-002", "b.go", 2)]
    actual = [_f("AI-001", "a.go", 1), _f("AI-003", "c.go", 3)]
    m = compute_metrics(expected=expected, actual=actual)
    assert m["tp"] == 1
    assert m["fp"] == 1
    assert m["fn"] == 1
    assert m["precision"] == 0.5
    assert m["recall"] == 0.5
    assert m["f1"] == 0.5


def test_compute_metrics_empty_inputs_yield_unit_f1():
    m = compute_metrics(expected=[], actual=[])
    assert m["f1"] == 1.0
