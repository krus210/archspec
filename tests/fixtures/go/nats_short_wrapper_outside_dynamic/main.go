package main

import "github.com/nats-io/nats.go"

// Bucket 5.6 (refined) fixture — the short-wrapper counterexample.
//
// PublishFooCreated has a body that fits in two lines. With the old fixed
// lookahead window of 30 lines, the suppression range would extend well
// past the wrapper's closing brace and silently swallow the independent
// dynamic publish in main() below. Brace-balanced ranges stop at the
// wrapper body's real closing brace, so the dynamic call below survives.
//
// IMPORTANT: this comment must NOT contain literal Publish-call syntax —
// the regex scanner does not strip Go comments, so embedding a sample
// like nc-dot-Publish-paren would create a phantom finding here at the
// comment line, which would mask whether the real call site (in main()
// further down) is being detected. See Bucket 5.8 in the plan file.

type Outbox struct{ nc *nats.Conn }

func (o *Outbox) PublishFooCreated(payload []byte) error {
	return o.nc.Publish("foo.created", payload)
}

func deriveSubject() string { return "" }

func main() {
	nc, _ := nats.Connect("nats://localhost:4222")
	// Independent dynamic publish — outside the wrapper body, must survive.
	_ = nc.Publish(deriveSubject(), nil)
}
