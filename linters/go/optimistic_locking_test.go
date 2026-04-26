package main

import (
	"path/filepath"
	"testing"
)

func TestOptimistic_OKNoFindings(t *testing.T) {
	dir := filepath.Join("testdata", "optimistic_locking", "ok")
	sm, _ := LoadServiceMap(filepath.Join(dir, "SERVICE_MAP.yaml"))
	got, _ := RunOptimisticLocking(sm, dir)
	if len(got) != 0 {
		t.Errorf("want 0, got %d: %+v", len(got), got)
	}
}

func TestOptimistic_MissingVersionPredicateFlagsAI003(t *testing.T) {
	dir := filepath.Join("testdata", "optimistic_locking", "bad")
	sm, _ := LoadServiceMap(filepath.Join(dir, "SERVICE_MAP.yaml"))
	got, _ := RunOptimisticLocking(sm, dir)
	if len(got) != 1 {
		t.Fatalf("want 1, got %d: %+v", len(got), got)
	}
	if got[0].Rule != "AI-003" || got[0].Severity != "BLOCK" {
		t.Errorf("rule=%q sev=%q", got[0].Rule, got[0].Severity)
	}
}

func TestOptimistic_SkipsWhenStrategyIsPessimistic(t *testing.T) {
	sm := &ServiceMap{}
	sm.Concurrency.Aggregates = []Aggregate{{Name: "x", WriteStrategy: "pessimistic"}}
	sm.GoExtensions.OptimisticLockingField = "row_version"
	got, _ := RunOptimisticLocking(sm, "testdata/optimistic_locking/bad")
	if len(got) != 0 {
		t.Errorf("pessimistic must skip; got %+v", got)
	}
}
