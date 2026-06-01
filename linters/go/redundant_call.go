package main

import (
	"go/ast"
	"go/token"
)

// RunRedundantCall flags a downstream singular method called inside a loop when a
// batch sibling exists in the scanned code (e.g. GetDistance in a loop while
// GetDistancesBatch is available) — an N+1 round-trip the batch call would collapse.
func RunRedundantCall(sm *ServiceMap, codeRoot string) ([]Finding, error) {
	files, err := WalkGoFiles(codeRoot, WalkOpts{})
	if err != nil {
		return nil, err
	}
	fset := token.NewFileSet()
	parsed := make([]*ast.File, 0, len(files))
	known := map[string]bool{}
	for _, p := range files {
		f, perr := ParseFile(fset, p)
		if perr != nil {
			continue
		}
		parsed = append(parsed, f)
		collectMethodNames(f, known)
	}

	var findings []Finding
	seen := map[token.Pos]bool{}
	for _, f := range parsed {
		ast.Inspect(f, func(n ast.Node) bool {
			var body *ast.BlockStmt
			switch x := n.(type) {
			case *ast.ForStmt:
				body = x.Body
			case *ast.RangeStmt:
				body = x.Body
			}
			if body == nil {
				return true
			}
			ast.Inspect(body, func(m ast.Node) bool {
				call, ok := m.(*ast.CallExpr)
				if !ok {
					return true
				}
				sel, ok := call.Fun.(*ast.SelectorExpr)
				if !ok || seen[call.Pos()] {
					return true
				}
				batch, ok := batchSibling(sel.Sel.Name, known)
				if !ok {
					return true
				}
				seen[call.Pos()] = true
				pos := fset.Position(call.Pos())
				findings = append(findings, Finding{
					Rule: "AI-008", Severity: "WARN",
					File:         relPath(pos.Filename, codeRoot),
					Line:         pos.Line,
					ContractRef:  sm.Path + " — dependencies.downstream (batch method available)",
					Message:      "call to " + sel.Sel.Name + "() inside a loop while batch method " + batch + "() exists — N+1 round-trips",
					SuggestedFix: "collect inputs and call " + batch + "() once outside the loop",
				})
				return true
			})
			return true
		})
	}
	return findings, nil
}

// collectMethodNames records every method name seen in the tree — from interface
// method specs, method declarations, AND call-site selectors. Collecting call sites
// (not just definitions) means a batch sibling defined in generated or external code
// (only ever seen as a call) still counts as "known".
func collectMethodNames(f *ast.File, known map[string]bool) {
	ast.Inspect(f, func(n ast.Node) bool {
		switch x := n.(type) {
		case *ast.CallExpr:
			if sel, ok := x.Fun.(*ast.SelectorExpr); ok {
				known[sel.Sel.Name] = true
			}
		case *ast.FuncDecl:
			if x.Recv != nil {
				known[x.Name.Name] = true
			}
		case *ast.InterfaceType:
			if x.Methods != nil {
				for _, m := range x.Methods.List {
					for _, nm := range m.Names {
						known[nm.Name] = true
					}
				}
			}
		}
		return true
	})
}

// batchSibling returns a known method that is the batch form of method, if any.
// Deterministic: candidates are checked in fixed order.
func batchSibling(method string, known map[string]bool) (string, bool) {
	for _, c := range []string{method + "Batch", method + "sBatch", method + "esBatch"} {
		if known[c] {
			return c, true
		}
	}
	return "", false
}
