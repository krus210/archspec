package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadServiceMap_FullFixturePassesThrough(t *testing.T) {
	repoRoot := repoRoot(t)
	yamlPath := filepath.Join(repoRoot, "tests", "fixtures", "yaml", "valid", "full.yaml")
	sm, err := LoadServiceMap(yamlPath)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if sm.Service.Language != "go" {
		t.Errorf("language = %q, want %q", sm.Service.Language, "go")
	}
	if sm.Path != yamlPath {
		t.Errorf("Path = %q, want %q", sm.Path, yamlPath)
	}
	if sm.GoExtensions.OutboxTable != "outbox_events" {
		t.Errorf("OutboxTable = %q, want %q", sm.GoExtensions.OutboxTable, "outbox_events")
	}
}

func TestLoadServiceMap_MissingFile(t *testing.T) {
	if _, err := LoadServiceMap(filepath.Join(t.TempDir(), "no.yaml")); err == nil {
		t.Fatal("expected error")
	}
}

func TestLoadServiceMap_ParsesDownstreamAndEvents(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "SERVICE_MAP.yaml")
	yaml := `service:
  name: matching-service
  language: go
dependencies:
  downstream:
    sync:
      - service: geo-service
        on_failure: degrade-gracefully
events:
  published:
    - topic: match.found
  consumed:
    - topic: task.created
`
	if err := os.WriteFile(p, []byte(yaml), 0o644); err != nil {
		t.Fatal(err)
	}
	sm, err := LoadServiceMap(p)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if len(sm.Dependencies.Downstream.Sync) != 1 || sm.Dependencies.Downstream.Sync[0].OnFailure != "degrade-gracefully" {
		t.Errorf("downstream sync not parsed: %+v", sm.Dependencies.Downstream.Sync)
	}
	if len(sm.Events.Published) != 1 || sm.Events.Published[0].Topic != "match.found" {
		t.Errorf("events.published not parsed: %+v", sm.Events.Published)
	}
	if len(sm.Events.Consumed) != 1 || sm.Events.Consumed[0].Topic != "task.created" {
		t.Errorf("events.consumed not parsed: %+v", sm.Events.Consumed)
	}
}

func repoRoot(t *testing.T) string {
	t.Helper()
	wd, _ := os.Getwd()
	return filepath.Clean(filepath.Join(wd, "..", ".."))
}
