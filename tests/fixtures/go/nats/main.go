package main

import (
	"context"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"
)

const (
	natsSubjectTaskCreated = "task.created"
	natsSubjectMatchFound  = "match.found"
)

func main() {
	nc, _ := nats.Connect("nats://localhost:4222")

	// Core NATS publish — identifier resolved via const table.
	_ = nc.Publish(natsSubjectTaskCreated, []byte("payload"))
	// Core NATS publish — string literal.
	_ = nc.Publish("billing.invoice.v1", []byte("payload"))
	// Runtime value — must NOT be recorded.
	type evt struct{ Subject string }
	e := evt{Subject: "x"}
	_ = nc.Publish(e.Subject, nil)

	// Core NATS subscribe — identifier resolved via const table.
	_, _ = nc.Subscribe(natsSubjectMatchFound, func(*nats.Msg) {})
	// Queue subscription — same shape, queue arg goes second.
	_, _ = nc.QueueSubscribe("notifications.push", "notif-workers", func(*nats.Msg) {})

	// JetStream publish.
	js, _ := jetstream.New(nc)
	_, _ = js.Publish(context.Background(), "geo.points.v1", []byte("payload"))
}
