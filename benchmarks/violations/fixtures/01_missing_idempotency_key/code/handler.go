package handler

import "net/http"

// CreateListing handler — declared idempotent in SERVICE_MAP, but does not read the header.
func CreateListing(w http.ResponseWriter, r *http.Request) {
	_ = r
	w.WriteHeader(http.StatusOK)
}
