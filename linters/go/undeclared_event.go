package main

import (
	"go/ast"
	"go/token"
	"strings"
)

// RunUndeclaredEvent flags NATS Publish/Subscribe to a topic (string literal or
// package-level string const) that is not declared in events.published /
// events.consumed. Conservative: only fires for subjects that resolve to a
// concrete, NATS-subject-shaped string. Runtime-built subjects are skipped.
func RunUndeclaredEvent(sm *ServiceMap, codeRoot string) ([]Finding, error) {
	published := map[string]bool{}
	for _, e := range sm.Events.Published {
		if e.Topic != "" {
			published[e.Topic] = true
		}
	}
	consumed := map[string]bool{}
	for _, e := range sm.Events.Consumed {
		if e.Topic != "" {
			consumed[e.Topic] = true
		}
	}

	files, err := WalkGoFiles(codeRoot, WalkOpts{})
	if err != nil {
		return nil, err
	}
	fset := token.NewFileSet()
	parsed := make([]*ast.File, 0, len(files))
	for _, p := range files {
		f, perr := ParseFile(fset, p)
		if perr != nil {
			continue
		}
		parsed = append(parsed, f)
	}

	// Flat namespace across files; on a same-name collision last-write-wins. That is
	// acceptable here — both values are concrete topics, so either resolves to a check.
	consts := map[string]string{}
	for _, f := range parsed {
		for _, decl := range f.Decls {
			gd, ok := decl.(*ast.GenDecl)
			if !ok || gd.Tok != token.CONST {
				continue
			}
			for _, spec := range gd.Specs {
				vs, ok := spec.(*ast.ValueSpec)
				if !ok {
					continue
				}
				for i, name := range vs.Names {
					if i < len(vs.Values) {
						if lit, ok := LiteralString(vs.Values[i]); ok {
							consts[name.Name] = lit
						}
					}
				}
			}
		}
	}
	resolve := func(e ast.Expr) (string, bool) {
		if lit, ok := LiteralString(e); ok {
			return lit, true
		}
		if id, ok := e.(*ast.Ident); ok {
			if v, ok := consts[id.Name]; ok {
				return v, true
			}
		}
		return "", false
	}

	var findings []Finding
	for _, f := range parsed {
		ast.Inspect(f, func(n ast.Node) bool {
			call, ok := n.(*ast.CallExpr)
			if !ok {
				return true
			}
			sel, ok := call.Fun.(*ast.SelectorExpr)
			if !ok || len(call.Args) == 0 {
				return true
			}
			var declared map[string]bool
			var dir string
			switch sel.Sel.Name {
			case "Publish":
				declared, dir = published, "published"
			case "Subscribe", "QueueSubscribe":
				declared, dir = consumed, "consumed"
			default:
				return true
			}
			topic, ok := resolve(call.Args[0])
			if !ok || !looksLikeTopic(topic) || declared[topic] {
				return true
			}
			pos := fset.Position(call.Pos())
			findings = append(findings, Finding{
				Rule: "AI-009", Severity: "BLOCK",
				File:         relPath(pos.Filename, codeRoot),
				Line:         pos.Line,
				ContractRef:  sm.Path + " — events." + dir,
				Message:      sel.Sel.Name + `("` + topic + `") but topic is not declared in events.` + dir,
				SuggestedFix: `add topic "` + topic + `" to events.` + dir + " in SERVICE_MAP.yaml",
			})
			return true
		})
	}
	return findings, nil
}

// looksLikeTopic keeps the BLOCK conservative: a NATS subject has a dot, at least
// one alphanumeric token, and only subject-legal characters. "hello" and "." are
// not topics; "task.failed" is.
func looksLikeTopic(s string) bool {
	if !strings.Contains(s, ".") {
		return false
	}
	sawAlnum := false
	for _, r := range s {
		switch {
		case r == '.' || r == '_' || r == '-' || r == '*' || r == '>':
		case r >= 'a' && r <= 'z', r >= 'A' && r <= 'Z', r >= '0' && r <= '9':
			sawAlnum = true
		default:
			return false
		}
	}
	return sawAlnum
}
