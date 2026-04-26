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

func repoRoot(t *testing.T) string {
	t.Helper()
	wd, _ := os.Getwd()
	return filepath.Clean(filepath.Join(wd, "..", ".."))
}
