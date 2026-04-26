package main

import (
	geov1 "example.com/gen/geo/v1"
	taskv1 "example.com/gen/task/v1"
	"google.golang.org/grpc"
)

func main() {
	s := grpc.NewServer()
	geov1.RegisterGeoServiceServer(s, nil)
	taskv1.RegisterTaskServiceServer(s, nil)
}
