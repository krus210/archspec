package main

import "github.com/nats-io/nats.go"

func computeSubject() string { return "x" }

func main() {
	nc, _ := nats.Connect("nats://localhost:4222")
	// Only dynamic publish in this file — no literal, no wrapper, no const resolution.
	_ = nc.Publish(computeSubject(), nil)
}
