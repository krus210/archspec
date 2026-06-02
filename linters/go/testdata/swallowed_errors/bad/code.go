package svc

type Client interface {
	RejectOffer(matchID, workerID string) error
	Fetch(id string) (string, error)
}

func handle(c Client) {
	_ = c.RejectOffer("m1", "w1")
	data, _ := c.Fetch("m1")
	_ = data
}
