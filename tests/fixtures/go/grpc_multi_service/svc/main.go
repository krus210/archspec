package main

import (
	"google.golang.org/grpc"

	billingv1 "example/proto/billing/v1"
)

type publicServer struct{ billingv1.UnimplementedBillingServiceServer }
type adminServer struct{ billingv1.UnimplementedBillingAdminServiceServer }

func main() {
	s := grpc.NewServer()
	// Bucket 5.1: each register call must enumerate only the matching
	// service-block RPCs from billing.proto.
	// Bucket 5.7: BillingAdminService domain-derives to `billing-admin`,
	// which has no matching proto/billing-admin/v1 tree. The fallback must
	// probe the proto already located for the public server (billing.proto)
	// and find the matching `service BillingAdminService { ... }` block.
	billingv1.RegisterBillingServiceServer(s, &publicServer{})
	billingv1.RegisterBillingAdminServiceServer(s, &adminServer{})
}
