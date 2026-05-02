package outbox

import "github.com/nats-io/nats.go"

type Outbox struct {
	nc *nats.Conn
}

// PublishMatchFound — outbox wrapper around nats.Publish. The subject literal
// `match.found` lives inside the method body, so the static scanner has to
// read forward to find it. Reproduces the freelance-marketplace pattern.
func (o *Outbox) PublishMatchFound(payload []byte) error {
	subject := "match.found"
	return o.nc.Publish(subject, payload)
}

// PublishTaskCreated — wrapper without an inline literal, so the scanner
// has to guess the topic from the method name (TaskCreated → task.created).
func (o *Outbox) PublishTaskCreated(payload []byte) error {
	return o.nc.Publish(deriveSubject(payload), payload)
}

func deriveSubject(_ []byte) string { return "" }
