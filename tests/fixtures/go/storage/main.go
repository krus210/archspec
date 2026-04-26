package main

import (
	"context"
	"database/sql"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/jmoiron/sqlx"
	"github.com/redis/go-redis/v9"
	"go.mongodb.org/mongo-driver/mongo"

	"example.com/services/geo-service/repository"
)

func main() {
	ctx := context.Background()
	_, _ = pgx.Connect(ctx, "postgres://localhost/db")
	_, _ = pgxpool.New(ctx, "postgres://localhost/db")
	_ = redis.NewClient(&redis.Options{Addr: "localhost:6379"})
	_, _ = mongo.Connect(ctx, nil)
	_, _ = sqlx.Open("postgres", "")
	_, _ = sql.Open("postgres", "")
	_ = repository.NewMemoryRepo()
}
