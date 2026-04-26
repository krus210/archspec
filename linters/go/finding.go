package main

import (
	"bytes"
	"encoding/json"
)

type Finding struct {
	Rule         string `json:"rule"`
	Severity     string `json:"severity"`
	File         string `json:"file"`
	Line         int    `json:"line"`
	ContractRef  string `json:"contract_ref"`
	Message      string `json:"message"`
	SuggestedFix string `json:"suggested_fix,omitempty"`
}

// EncodeFindings emits one JSON array, never null.
func EncodeFindings(findings []Finding) []byte {
	if findings == nil {
		findings = []Finding{}
	}
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	_ = enc.Encode(findings)
	return buf.Bytes()
}
