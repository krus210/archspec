package main

import (
	"errors"
	"flag"
	"fmt"
	"os"
	"sort"
)

type runner func(*ServiceMap, string) ([]Finding, error)

var subcommands = map[string]runner{
	"handler-idempotency": RunHandlerIdempotency,
	"outbox-pattern":      RunOutboxPattern,
	"optimistic-locking":  RunOptimisticLocking,
	"swallowed-errors":    RunSwallowedErrors,
	"redundant-call":      RunRedundantCall,
	"undeclared-event":    RunUndeclaredEvent,
}

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	sub := os.Args[1]
	fn, ok := subcommands[sub]
	if !ok {
		fmt.Fprintf(os.Stderr, "unknown subcommand: %s\n", sub)
		usage()
		os.Exit(2)
	}
	fs := flag.NewFlagSet(sub, flag.ContinueOnError)
	smPath := fs.String("service-map", "docs/SERVICE_MAP.yaml", "path to SERVICE_MAP.yaml")
	codeRoot := fs.String("code", ".", "path to source root to scan")
	if err := fs.Parse(os.Args[2:]); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			os.Exit(0)
		}
		os.Exit(2)
	}
	sm, err := LoadServiceMap(*smPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	findings, err := fn(sm, *codeRoot)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	os.Stdout.Write(EncodeFindings(findings))
	if len(findings) > 0 {
		os.Exit(1)
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: archspec-go-linter <subcommand> [--service-map PATH] [--code DIR]")
	fmt.Fprintln(os.Stderr, "subcommands:")
	names := make([]string, 0, len(subcommands))
	for name := range subcommands {
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		fmt.Fprintln(os.Stderr, "  "+name)
	}
}
