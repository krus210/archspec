package main

import (
	"path/filepath"
	"testing"
)

func TestOutbox_OKVariantNoFindings(t *testing.T) {
	dir := filepath.Join("testdata", "outbox_pattern", "ok")
	sm, _ := LoadServiceMap(filepath.Join(dir, "SERVICE_MAP.yaml"))
	got, _ := RunOutboxPattern(sm, dir)
	if len(got) != 0 {
		t.Errorf("want 0, got %d: %+v", len(got), got)
	}
}

func TestOutbox_BadVariantFlagsAI002(t *testing.T) {
	dir := filepath.Join("testdata", "outbox_pattern", "bad")
	sm, _ := LoadServiceMap(filepath.Join(dir, "SERVICE_MAP.yaml"))
	got, _ := RunOutboxPattern(sm, dir)
	if len(got) != 1 {
		t.Fatalf("want 1, got %d: %+v", len(got), got)
	}
	if got[0].Rule != "AI-002" || got[0].Severity != "BLOCK" {
		t.Errorf("rule=%q sev=%q", got[0].Rule, got[0].Severity)
	}
}

func TestOutbox_OnlyActiveWhenPatternIsOutbox(t *testing.T) {
	sm := &ServiceMap{}
	sm.Consistency.WritePath.Pattern = "direct"
	got, _ := RunOutboxPattern(sm, "testdata/outbox_pattern/bad")
	if len(got) != 0 {
		t.Errorf("must skip when pattern != outbox; got %+v", got)
	}
}
