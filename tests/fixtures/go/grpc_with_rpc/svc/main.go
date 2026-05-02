package main

import (
	"google.golang.org/grpc"

	ordersv1 "example/proto/orders/v1"
)

type orderServer struct{ ordersv1.UnimplementedOrderServiceServer }

func main() {
	s := grpc.NewServer()
	ordersv1.RegisterOrderServiceServer(s, &orderServer{})
}
