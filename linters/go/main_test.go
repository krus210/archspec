package main

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"testing"
)

var (
	binPath  string
	binBuild sync.Once
	binErr   error
)

func buildBin(t *testing.T) string {
	t.Helper()
	binBuild.Do(func() {
		dir, err := os.MkdirTemp("", "archspec-go-linter-bin-*")
		if err != nil {
			binErr = err
			return
		}
		binPath = filepath.Join(dir, "archspec-go-linter")
		out, err := exec.Command("go", "build", "-o", binPath, ".").CombinedOutput()
		if err != nil {
			binErr = &buildError{out: string(out), err: err}
		}
	})
	if binErr != nil {
		t.Fatalf("build: %v", binErr)
	}
	return binPath
}

type buildError struct {
	out string
	err error
}

func (b *buildError) Error() string { return b.err.Error() + ": " + b.out }

func runBin(t *testing.T, args ...string) (string, string, int) {
	t.Helper()
	bin := buildBin(t)
	cmd := exec.Command(bin, args...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()
	exit := 0
	if ee, ok := err.(*exec.ExitError); ok {
		exit = ee.ExitCode()
	} else if err != nil {
		t.Fatalf("run: %v", err)
	}
	return stdout.String(), stderr.String(), exit
}

func TestUsageOnNoArgs(t *testing.T) {
	_, stderr, exit := runBin(t)
	if exit != 2 {
		t.Errorf("want exit=2, got %d (%s)", exit, stderr)
	}
	if !strings.Contains(stderr, "usage:") {
		t.Errorf("usage missing: %q", stderr)
	}
}

func TestRunHandlerIdempotencySubcommand(t *testing.T) {
	dir := filepath.Join("testdata", "handler_idempotency", "bad")
	stdout, _, exit := runBin(t,
		"handler-idempotency",
		"--service-map", filepath.Join(dir, "SERVICE_MAP.yaml"),
		"--code", dir,
	)
	if exit != 1 {
		t.Errorf("want exit=1 (findings), got %d", exit)
	}
	if !strings.Contains(stdout, `"rule":"AI-001"`) {
		t.Errorf("expected AI-001 finding, got: %s", stdout)
	}
}

func TestUnknownSubcommand(t *testing.T) {
	_, stderr, exit := runBin(t, "wat")
	if exit != 2 {
		t.Errorf("want exit=2, got %d (%s)", exit, stderr)
	}
}
