package main

import "github.com/nats-io/nats.go"

// Bucket 5.6 fixture: a literal publish AND an independent dynamic publish in
// the same file, neither of which is wrapped in a `func PublishX(...)`
// helper. The dynamic call site is real and must surface as `<dynamic>` —
// suppressing it just because the file also has a literal would silently lose
// publish coverage.

func deriveSubject() string { return "" }

func main() {
	nc, _ := nats.Connect("nats://localhost:4222")

	// Resolved literal — surfaces as a normal medium-confidence finding.
	_ = nc.Publish("foo.created", []byte("payload"))

	// Independent dynamic publish — must NOT be suppressed by the literal
	// above (different call site, no wrapper relationship).
	_ = nc.Publish(deriveSubject(), nil)
}
