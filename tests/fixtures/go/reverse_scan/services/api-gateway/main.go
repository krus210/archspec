package main

import (
	"context"

	geov1 "example.com/gen/geo/v1"
	"google.golang.org/grpc"
)

func run(conn *grpc.ClientConn) {
	c := geov1.NewGeoServiceClient(conn)
	_, _ = c.GetCity(context.Background(), &geov1.GetCityRequest{Id: "1"})
	_, _ = c.GetDistance(context.Background(), &geov1.GetDistanceRequest{From: "a", To: "b"})
}
