package repo

import "context"

type DB interface{ Exec(ctx context.Context, q string, args ...any) error }

func UpdateListing(ctx context.Context, db DB, id int, title string) error {
	return db.Exec(ctx, `UPDATE listings SET title=$1 WHERE id=$2`, title, id) // missing row_version
}
