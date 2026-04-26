package main

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestFindingJSONShape(t *testing.T) {
	f := Finding{
		Rule:         "AI-001",
		Severity:     "BLOCK",
		File:         "internal/handler/x.go",
		Line:         42,
		ContractRef:  "SERVICE_MAP.yaml:78",
		Message:      "missing X-Idempotency-Key",
		SuggestedFix: "r.Header.Get(\"X-Idempotency-Key\")",
	}
	out, err := json.Marshal(f)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	got := string(out)
	for _, want := range []string{
		`"rule":"AI-001"`, `"severity":"BLOCK"`,
		`"file":"internal/handler/x.go"`, `"line":42`,
		`"contract_ref":"SERVICE_MAP.yaml:78"`,
		`"message":"missing X-Idempotency-Key"`,
		`"suggested_fix":`,
	} {
		if !strings.Contains(got, want) {
			t.Errorf("missing %q in %s", want, got)
		}
	}
}

func TestEncodeFindingsEmptyArrayNotNull(t *testing.T) {
	out := EncodeFindings(nil)
	if string(out) != "[]\n" {
		t.Errorf("want []\\n, got %q", string(out))
	}
}
