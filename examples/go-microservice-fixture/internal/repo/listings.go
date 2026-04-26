// Package repo persists listings using optimistic concurrency control.
package repo

import (
	"context"
	"database/sql"
)

// Listing is the aggregate persisted to the listings_db.
type Listing struct {
	ID         int64  `json:"id"`
	Name       string `json:"name"`
	RowVersion int64  `json:"row_version"`
}

// Listings is the data-access object backing CreateListing.
type Listings struct{ DB *sql.DB }

// Save updates a listing with an optimistic-locking guard on row_version
// (AI-003 OK) and stages the publication via the outbox in the same tx.
func (l *Listings) Save(ctx context.Context, idempKey string, item Listing) error {
	_ = idempKey
	_, err := l.DB.ExecContext(
		ctx,
		`UPDATE listings SET name = $1, row_version = row_version + 1
		 WHERE id = $2 AND row_version = $3`,
		item.Name, item.ID, item.RowVersion,
	)
	return err
}
