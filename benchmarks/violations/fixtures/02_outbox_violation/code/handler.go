package svc

import "context"

type Repo interface{ Save(ctx context.Context, x any) error }
type Publisher interface{ Publish(ctx context.Context, e any) error }

func Create(ctx context.Context, repo Repo, pub Publisher, item any, evt any) error {
	if err := repo.Save(ctx, item); err != nil {
		return err
	}
	return pub.Publish(ctx, evt) // violation: direct publish after Save instead of writing to outbox.
}
