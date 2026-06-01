package svc

type Client interface {
	RejectOffer(matchID, workerID string) error
}

func handle(c Client) {
	_ = c.RejectOffer("m1", "w1")
}
