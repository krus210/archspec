package svc

import "context"

type Repo interface{ Save(ctx context.Context, x any) error }
type Outbox interface{ Append(ctx context.Context, e any) error }

func Create(ctx context.Context, repo Repo, ob Outbox, item any, evt any) error {
	if err := repo.Save(ctx, item); err != nil {
		return err
	}
	return ob.Append(ctx, evt)
}
