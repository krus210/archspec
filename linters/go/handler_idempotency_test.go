package main

import (
	"path/filepath"
	"testing"
)

func TestHandlerIdempotency_OKHandlerProducesNoFindings(t *testing.T) {
	dir := filepath.Join("testdata", "handler_idempotency", "ok")
	sm, _ := LoadServiceMap(filepath.Join(dir, "SERVICE_MAP.yaml"))
	got, err := RunHandlerIdempotency(sm, dir)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 0 {
		t.Errorf("want 0, got %d: %+v", len(got), got)
	}
}

func TestHandlerIdempotency_BadHandlerFlagsAI001(t *testing.T) {
	dir := filepath.Join("testdata", "handler_idempotency", "bad")
	sm, _ := LoadServiceMap(filepath.Join(dir, "SERVICE_MAP.yaml"))
	got, err := RunHandlerIdempotency(sm, dir)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 {
		t.Fatalf("want 1 finding, got %d: %+v", len(got), got)
	}
	if got[0].Rule != "AI-001" || got[0].Severity != "BLOCK" {
		t.Errorf("rule=%q sev=%q", got[0].Rule, got[0].Severity)
	}
}
