package handler

import (
	"context"

	geov1 "example.com/gen/geo/v1"
)

type Handler struct {
	geo geov1.GeoServiceClient
}

func (h *Handler) Match(ctx context.Context) error {
	_, err := h.geo.GetDistance(ctx, &geov1.GetDistanceRequest{From: "a", To: "b"})
	return err
}
