package repo

import "context"

type DB interface{ Exec(ctx context.Context, q string, args ...any) error }

func UpdateListing(ctx context.Context, db DB, id, version int, title string) error {
	return db.Exec(ctx,
		`UPDATE listings SET title=$1, row_version=row_version+1 WHERE id=$2 AND row_version=$3`,
		title, id, version)
}
