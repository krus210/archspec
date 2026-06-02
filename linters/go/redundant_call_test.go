package main

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestRunRedundantCallSubcommand(t *testing.T) {
	bad := filepath.Join("testdata", "redundant_call", "bad")
	stdout, _, exit := runBin(t,
		"redundant-call",
		"--service-map", filepath.Join(bad, "SERVICE_MAP.yaml"),
		"--code", bad,
	)
	if exit != 1 {
		t.Errorf("bad: want exit=1 (findings), got %d (%s)", exit, stdout)
	}
	if !strings.Contains(stdout, `"rule":"AI-008"`) {
		t.Errorf("bad: expected AI-008 finding, got: %s", stdout)
	}
	if !strings.Contains(stdout, `"severity":"WARN"`) {
		t.Errorf("bad: expected WARN severity, got: %s", stdout)
	}
	if !strings.Contains(stdout, "GetDistancesBatch") {
		t.Errorf("bad: message should name the batch sibling, got: %s", stdout)
	}
	if !strings.Contains(stdout, "GetDistance(") {
		t.Errorf("bad: message should name the singular call GetDistance(), got: %s", stdout)
	}

	ok := filepath.Join("testdata", "redundant_call", "ok")
	stdout, _, exit = runBin(t,
		"redundant-call",
		"--service-map", filepath.Join(ok, "SERVICE_MAP.yaml"),
		"--code", ok,
	)
	if exit != 0 {
		t.Errorf("ok: want exit=0, got %d (%s)", exit, stdout)
	}
}

func TestBatchSibling(t *testing.T) {
	known := map[string]bool{"GetDistancesBatch": true, "FetchBatch": true}
	cases := []struct {
		method string
		want   string
		ok     bool
	}{
		{"GetDistance", "GetDistancesBatch", true}, // matches via the "sBatch" candidate
		{"Fetch", "FetchBatch", true},              // matches via the "Batch" candidate
		{"GetWorker", "", false},                   // no batch sibling present
	}
	for _, tc := range cases {
		got, ok := batchSibling(tc.method, known)
		if got != tc.want || ok != tc.ok {
			t.Errorf("batchSibling(%q) = (%q, %v), want (%q, %v)", tc.method, got, ok, tc.want, tc.ok)
		}
	}
}
