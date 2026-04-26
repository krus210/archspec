package main

import (
	"go/ast"
	"go/token"
	"regexp"
	"strings"
)

var updateRe = regexp.MustCompile(`(?is)\bUPDATE\b\s+\w+\s+SET\b`)

// RunOptimisticLocking flags SQL-like string literals that issue UPDATE statements
// without a `WHERE ... <version_field> ...` predicate, when at least one aggregate
// is declared with write_strategy=optimistic.
func RunOptimisticLocking(sm *ServiceMap, codeRoot string) ([]Finding, error) {
	hasOptimistic := false
	for _, a := range sm.Concurrency.Aggregates {
		if a.WriteStrategy == "optimistic" {
			hasOptimistic = true
			break
		}
	}
	if !hasOptimistic {
		return nil, nil
	}
	field := sm.GoExtensions.OptimisticLockingField
	if field == "" {
		field = "row_version"
	}
	files, err := WalkGoFiles(codeRoot, WalkOpts{})
	if err != nil {
		return nil, err
	}
	fset := token.NewFileSet()
	var findings []Finding
	for _, p := range files {
		f, perr := ParseFile(fset, p)
		if perr != nil {
			continue
		}
		ast.Inspect(f, func(n ast.Node) bool {
			lit, ok := n.(*ast.BasicLit)
			if !ok || lit.Kind != token.STRING {
				return true
			}
			val := strings.Trim(lit.Value, "`\"")
			if !updateRe.MatchString(val) {
				return true
			}
			lower := strings.ToLower(val)
			if !strings.Contains(lower, "where") {
				return true // not our concern; UPDATE without WHERE is its own bug
			}
			// Need both `<field>=` (in SET) and `<field>=` or `<field> =` in the WHERE clause.
			if strings.Contains(lower, strings.ToLower(field)) &&
				strings.Count(lower, strings.ToLower(field)) >= 2 {
				return true
			}
			pos := fset.Position(lit.Pos())
			findings = append(findings, Finding{
				Rule: "AI-003", Severity: "BLOCK",
				File:         relPath(pos.Filename, codeRoot),
				Line:         pos.Line,
				ContractRef:  sm.Path + " — concurrency.aggregates[*].write_strategy: optimistic",
				Message:      "UPDATE missing optimistic-lock predicate on column `" + field + "`",
				SuggestedFix: "append `AND " + field + " = ?` and bump the column in SET",
			})
			return true
		})
	}
	return findings, nil
}
