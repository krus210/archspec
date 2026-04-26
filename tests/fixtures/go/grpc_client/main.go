package main

import (
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

const (
	defaultTaskServiceAddr = "localhost:50052"
	defaultGeoServiceAddr  = "localhost:50060"
)

func main() {
	taskAddr := defaultTaskServiceAddr
	geoAddr := defaultGeoServiceAddr

	_, _ = grpc.NewClient(taskAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	_, _ = grpc.Dial(geoAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))

	// Direct literal address.
	_, _ = grpc.NewClient("matching-service:50053", grpc.WithTransportCredentials(insecure.NewCredentials()))
}
