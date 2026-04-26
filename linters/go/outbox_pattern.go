package main

import (
	"go/ast"
	"go/token"
)

// RunOutboxPattern flags functions that call <repo>.Save(...) and then,
// in the same function body, call <publisher>.Publish(...). When write_path.pattern
// is "outbox", the second call must instead append to the outbox table.
func RunOutboxPattern(sm *ServiceMap, codeRoot string) ([]Finding, error) {
	if sm.Consistency.WritePath.Pattern != "outbox" {
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
			fd, ok := n.(*ast.FuncDecl)
			if !ok || fd.Body == nil {
				return true
			}
			savePos := token.NoPos
			for _, stmt := range fd.Body.List {
				ast.Inspect(stmt, func(node ast.Node) bool {
					call, ok := node.(*ast.CallExpr)
					if !ok {
						return true
					}
					sel, ok := call.Fun.(*ast.SelectorExpr)
					if !ok {
						return true
					}
					switch sel.Sel.Name {
					case "Save":
						savePos = call.Pos()
					case "Publish":
						if savePos.IsValid() {
							pos := fset.Position(call.Pos())
							findings = append(findings, Finding{
								Rule: "AI-002", Severity: "BLOCK",
								File:         relPath(pos.Filename, codeRoot),
								Line:         pos.Line,
								ContractRef:  sm.Path + " — consistency.write_path.pattern: outbox",
								Message:      "direct Publish after Save violates outbox pattern",
								SuggestedFix: "append the event to outbox_table (`" + sm.GoExtensions.OutboxTable + "`) within the same transaction",
							})
						}
					}
					return true
				})
			}
			return true
		})
	}
	return findings, nil
}
