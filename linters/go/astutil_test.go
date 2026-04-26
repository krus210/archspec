package main

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestWalkGoFilesSkipsTestFilesAndVendorByDefault(t *testing.T) {
	got, err := WalkGoFiles("testdata/astutil", WalkOpts{})
	if err != nil {
		t.Fatal(err)
	}
	for _, p := range got {
		if strings.HasSuffix(p, "_test.go") {
			t.Errorf("must skip _test.go: %s", p)
		}
		if strings.Contains(p, string(filepath.Separator)+"vendor"+string(filepath.Separator)) {
			t.Errorf("must skip vendor/: %s", p)
		}
	}
}
