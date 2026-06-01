package svc

import "log"

type Client interface {
	RejectOffer(matchID, workerID string) error
}

func handle(c Client) error {
	if err := c.RejectOffer("m1", "w1"); err != nil {
		log.Printf("reject failed: %v", err)
		return err
	}
	return nil
}
