package db

import (
	"context"
	"fmt"
	"os"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Resource struct {
	ID       string
	Name     string
	Type     string
	Region   string
	Tags     map[string]*string
	Active   bool
	LastSeen time.Time
}

var (
	pool *pgxpool.Pool
	once sync.Once
)

func Connect() (*pgxpool.Pool, error) {
	var err error
	once.Do(func() {
		dbURL := os.Getenv("DATABASE_URL")
		if dbURL == "" {
			dbURL = "postgresql://postgres:postgres@localhost:5432/cloudreaper"
		}
		pool, err = pgxpool.New(context.Background(), dbURL)
	})
	return pool, err
}

func UpsertResources(resources []Resource) error {
	db, err := Connect()
	if err != nil {
		return err
	}

	batch := &pgx.Batch{}
	for _, r := range resources {
		sql := `
			INSERT INTO resources (id, name, type, region, tags, active, last_seen)
			VALUES ($1, $2, $3, $4, $5, $6, $7)
			ON CONFLICT (id) DO UPDATE SET
				name = EXCLUDED.name,
				type = EXCLUDED.type,
				region = EXCLUDED.region,
				tags = EXCLUDED.tags,
				active = EXCLUDED.active,
				last_seen = EXCLUDED.last_seen
		`
		batch.Queue(sql, r.ID, r.Name, r.Type, r.Region, r.Tags, r.Active, r.LastSeen)
	}

	br := db.SendBatch(context.Background(), batch)
	defer br.Close()

	for i := 0; i < len(resources); i++ {
		_, err := br.Exec()
		if err != nil {
			return fmt.Errorf("error in batch exec at index %d: %v", i, err)
		}
	}

	return nil
}
