package main

import (
	"go/ast"
	"go/token"
	"strings"
)

// RunHandlerIdempotency scans Go files under codeRoot and reports endpoints that
// declare idempotency.required=true but whose handler funcs never read the
// configured header (`X-Idempotency-Key` extracted from key_source).
func RunHandlerIdempotency(sm *ServiceMap, codeRoot string) ([]Finding, error) {
	var requiredEndpoints []Endpoint
	for _, ep := range sm.API.Endpoints {
		if ep.Idempotency.Required {
			requiredEndpoints = append(requiredEndpoints, ep)
		}
	}
	if len(requiredEndpoints) == 0 {
		return nil, nil
	}

	files, err := WalkGoFiles(codeRoot, WalkOpts{})
	if err != nil {
		return nil, err
	}

	fset := token.NewFileSet()
	type funcInfo struct {
		Name     string
		Pos      token.Position
		ReadsHdr map[string]bool
	}
	funcs := make(map[string]*funcInfo)

	for _, p := range files {
		f, perr := ParseFile(fset, p)
		if perr != nil {
			continue
		}
		for _, decl := range f.Decls {
			fd, ok := decl.(*ast.FuncDecl)
			if !ok {
				continue
			}
			info := &funcInfo{
				Name:     fd.Name.Name,
				Pos:      fset.Position(fd.Pos()),
				ReadsHdr: map[string]bool{},
			}
			ast.Inspect(fd, func(n ast.Node) bool {
				call, ok := n.(*ast.CallExpr)
				if !ok || !CallExprMatches(call, "Header", "Get") {
					return true
				}
				if len(call.Args) == 1 {
					if lit, ok := LiteralString(call.Args[0]); ok {
						info.ReadsHdr[strings.ToLower(lit)] = true
					}
				}
				return true
			})
			funcs[fd.Name.Name] = info
		}
	}

	var findings []Finding
	for _, ep := range requiredEndpoints {
		header := strings.ToLower(extractHeaderName(ep.Idempotency.KeySource))
		fn, ok := funcs[ep.Name]
		if !ok {
			findings = append(findings, Finding{
				Rule: "AI-001", Severity: "BLOCK",
				ContractRef:  sm.Path + " — endpoint " + ep.Name,
				Message:      "endpoint declared idempotency.required=true but no matching handler function found",
				SuggestedFix: "name the handler function exactly `" + ep.Name + "` or add a registration mapping",
			})
			continue
		}
		if header != "" && !fn.ReadsHdr[header] {
			findings = append(findings, Finding{
				Rule: "AI-001", Severity: "BLOCK",
				File:         relPath(fn.Pos.Filename, codeRoot),
				Line:         fn.Pos.Line,
				ContractRef:  sm.Path + " — endpoint " + ep.Name,
				Message:      "handler does not read declared idempotency key " + header,
				SuggestedFix: "key := r.Header.Get(\"" + extractHeaderName(ep.Idempotency.KeySource) + "\")",
			})
		}
	}
	return findings, nil
}

func extractHeaderName(keySource string) string {
	// "header: X-Idempotency-Key" → "X-Idempotency-Key"
	parts := strings.SplitN(keySource, ":", 2)
	if len(parts) != 2 {
		return ""
	}
	return strings.TrimSpace(parts[1])
}

func relPath(abs, root string) string {
	if strings.HasPrefix(abs, root) {
		return strings.TrimPrefix(strings.TrimPrefix(abs, root), "/")
	}
	return abs
}
