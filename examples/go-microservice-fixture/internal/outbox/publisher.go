// Package outbox stages domain events for asynchronous publication.
package outbox

import (
	"context"
	"database/sql"
)

// Insert writes the event into the outbox_events table; a separate dispatcher
// publishes from there. Direct publishing is forbidden by AI-002 in this service.
func Insert(ctx context.Context, db *sql.DB, topic string, payload []byte) error {
	_, err := db.ExecContext(ctx, `INSERT INTO outbox_events (topic, payload) VALUES ($1, $2)`, topic, payload)
	return err
}
