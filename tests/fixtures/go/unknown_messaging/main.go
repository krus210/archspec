package main

// Fictitious messaging library — must produce zero events without raising.

type someBroker struct{}

func (s *someBroker) Send(topic string, payload []byte) error    { return nil }
func (s *someBroker) Listen(topic string, fn func([]byte)) error { return nil }

func newSomeBroker(addr string) *someBroker { return &someBroker{} }

func main() {
	b := newSomeBroker("broker:1234")
	_ = b.Send("orders.placed", []byte("payload"))
	_ = b.Listen("orders.shipped", func([]byte) {})
}
