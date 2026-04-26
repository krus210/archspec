package handler

import "net/http"

func CreateListing(w http.ResponseWriter, r *http.Request) {
	key := r.Header.Get("X-Idempotency-Key")
	if key == "" {
		http.Error(w, "missing key", http.StatusBadRequest)
		return
	}
	_ = key
	w.WriteHeader(http.StatusOK)
}
