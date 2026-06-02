package main

import (
	"go/ast"
	"go/token"
	"strings"
)

// RunSwallowedErrors flags `_ = recv.Method(...)` blank-assignments of a method
// call when the contract declares a downstream sync dependency with an on_failure
// policy — the returned error (and everything else) is silently discarded.
func RunSwallowedErrors(sm *ServiceMap, codeRoot string) ([]Finding, error) {
	hasPolicy := false
	for _, d := range sm.Dependencies.Downstream.Sync {
		if strings.TrimSpace(d.OnFailure) != "" {
			hasPolicy = true
			break
		}
	}
	if !hasPolicy {
		return nil, nil
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
			as, ok := n.(*ast.AssignStmt)
			if !ok || len(as.Lhs) == 0 || len(as.Rhs) != 1 {
				return true
			}
			anyBlank := false
			for _, lhs := range as.Lhs {
				if id, ok := lhs.(*ast.Ident); ok && id.Name == "_" {
					anyBlank = true
					break
				}
			}
			if !anyBlank {
				return true
			}
			call, ok := as.Rhs[0].(*ast.CallExpr)
			if !ok {
				return true
			}
			sel, ok := call.Fun.(*ast.SelectorExpr)
			if !ok {
				return true
			}
			pos := fset.Position(as.Pos())
			findings = append(findings, Finding{
				Rule: "AI-007", Severity: "WARN",
				File:         relPath(pos.Filename, codeRoot),
				Line:         pos.Line,
				ContractRef:  sm.Path + " — dependencies.downstream.sync[].on_failure",
				Message:      "call " + selName(sel) + " discards a return value via `_` — a downstream error may be swallowed",
				SuggestedFix: "capture the error and handle it per the declared on_failure policy",
			})
			return true
		})
	}
	return findings, nil
}

func selName(sel *ast.SelectorExpr) string {
	switch x := sel.X.(type) {
	case *ast.Ident:
		return x.Name + "." + sel.Sel.Name
	case *ast.SelectorExpr:
		return x.Sel.Name + "." + sel.Sel.Name
	}
	return sel.Sel.Name
}
