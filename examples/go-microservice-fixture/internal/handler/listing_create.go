// Package handler exposes the HTTP handlers for the listings service.
package handler

import (
	"encoding/json"
	"net/http"

	"github.com/example/listings-svc/internal/repo"
)

// CreateListing reads X-Idempotency-Key (AI-001 OK) and persists via the outbox
// table only — no direct publisher.Publish (AI-002 OK).
func CreateListing(repository *repo.Listings) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		idempKey := r.Header.Get("X-Idempotency-Key")
		if idempKey == "" {
			http.Error(w, "missing X-Idempotency-Key", http.StatusBadRequest)
			return
		}
		var item repo.Listing
		if err := json.NewDecoder(r.Body).Decode(&item); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		if err := repository.Save(r.Context(), idempKey, item); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusCreated)
	}
}
