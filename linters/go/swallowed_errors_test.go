package main

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestRunSwallowedErrorsSubcommand(t *testing.T) {
	bad := filepath.Join("testdata", "swallowed_errors", "bad")
	stdout, _, exit := runBin(t,
		"swallowed-errors",
		"--service-map", filepath.Join(bad, "SERVICE_MAP.yaml"),
		"--code", bad,
	)
	if exit != 1 {
		t.Errorf("bad: want exit=1 (findings), got %d (%s)", exit, stdout)
	}
	if !strings.Contains(stdout, `"rule":"AI-007"`) {
		t.Errorf("bad: expected AI-007 finding, got: %s", stdout)
	}
	if !strings.Contains(stdout, `"severity":"WARN"`) {
		t.Errorf("bad: expected WARN severity, got: %s", stdout)
	}
	if !strings.Contains(stdout, "RejectOffer") || !strings.Contains(stdout, "Fetch") {
		t.Errorf("bad: should flag both `_ = c.RejectOffer(...)` and `data, _ := c.Fetch(...)`, got: %s", stdout)
	}

	ok := filepath.Join("testdata", "swallowed_errors", "ok")
	stdout, _, exit = runBin(t,
		"swallowed-errors",
		"--service-map", filepath.Join(ok, "SERVICE_MAP.yaml"),
		"--code", ok,
	)
	if exit != 0 {
		t.Errorf("ok: want exit=0, got %d (%s)", exit, stdout)
	}
}

func TestSwallowedErrors_GateOffWhenNoOnFailure(t *testing.T) {
	sm := &ServiceMap{} // no downstream sync / no on_failure → gate off
	findings, err := RunSwallowedErrors(sm, filepath.Join("testdata", "swallowed_errors", "bad"))
	if err != nil {
		t.Fatal(err)
	}
	if len(findings) != 0 {
		t.Errorf("gate off: want 0 findings, got %d: %+v", len(findings), findings)
	}
}
