package main

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestRunUndeclaredEventSubcommand(t *testing.T) {
	bad := filepath.Join("testdata", "undeclared_event", "bad")
	stdout, _, exit := runBin(t,
		"undeclared-event",
		"--service-map", filepath.Join(bad, "SERVICE_MAP.yaml"),
		"--code", bad,
	)
	if exit != 1 {
		t.Errorf("bad: want exit=1 (findings), got %d (%s)", exit, stdout)
	}
	if !strings.Contains(stdout, `"rule":"AI-009"`) {
		t.Errorf("bad: expected AI-009 finding, got: %s", stdout)
	}
	if !strings.Contains(stdout, "task.failed") {
		t.Errorf("bad: message should name the undeclared topic, got: %s", stdout)
	}
	if !strings.Contains(stdout, `"severity":"WARN"`) {
		t.Errorf("bad: expected WARN severity, got: %s", stdout)
	}
	if !strings.Contains(stdout, "task.unknown") {
		t.Errorf("bad: expected the undeclared subscribe topic task.unknown, got: %s", stdout)
	}

	ok := filepath.Join("testdata", "undeclared_event", "ok")
	stdout, _, exit = runBin(t,
		"undeclared-event",
		"--service-map", filepath.Join(ok, "SERVICE_MAP.yaml"),
		"--code", ok,
	)
	if exit != 0 {
		t.Errorf("ok: want exit=0, got %d (%s)", exit, stdout)
	}
}

func TestLooksLikeTopic(t *testing.T) {
	cases := []struct {
		s    string
		want bool
	}{
		{"task.failed", true},
		{"match.found.v2", true},
		{"orders.*", true},
		{"hello", false},         // no dot
		{".", false},             // no alphanumeric
		{"bad subject.x", false}, // space is illegal
	}
	for _, tc := range cases {
		if got := looksLikeTopic(tc.s); got != tc.want {
			t.Errorf("looksLikeTopic(%q) = %v, want %v", tc.s, got, tc.want)
		}
	}
}
