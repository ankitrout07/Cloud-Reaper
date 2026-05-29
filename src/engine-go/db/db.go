package db

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Resource struct {
	ID            string
	Name          string
	Type          string
	Region        string
	Tags          map[string]*string
	Active        bool
	IsProtected   bool
	IsUnallocated bool
	LastSeen      time.Time
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
			INSERT INTO resources (id, name, type, region, tags, active, is_protected, is_unallocated, last_seen)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
			ON CONFLICT (id) DO UPDATE SET
				name = EXCLUDED.name,
				type = EXCLUDED.type,
				region = EXCLUDED.region,
				tags = EXCLUDED.tags,
				active = EXCLUDED.active,
				is_protected = EXCLUDED.is_protected,
				is_unallocated = EXCLUDED.is_unallocated,
				last_seen = EXCLUDED.last_seen
		`
		batch.Queue(sql, r.ID, r.Name, r.Type, r.Region, r.Tags, r.Active, r.IsProtected, r.IsUnallocated, r.LastSeen)
	}

	br := db.SendBatch(context.Background(), batch)
	defer func() {
		_ = br.Close()
	}()

	for i := 0; i < len(resources); i++ {
		_, err := br.Exec()
		if err != nil {
			return fmt.Errorf("error in batch exec at index %d: %w", i, err)
		}
	}

	return nil
}

func CleanupInactiveResources(lastScanStart time.Time) error {
	db, err := Connect()
	if err != nil {
		return err
	}
	_, err = db.Exec(context.Background(), "UPDATE resources SET active = false WHERE last_seen < $1", lastScanStart)
	return err
}

func AddBusinessMetric(metricName string, value float64, unit string) error {
	db, err := Connect()
	if err != nil {
		return err
	}
	_, err = db.Exec(context.Background(), "INSERT INTO business_metrics (metric_name, value, unit, date) VALUES ($1, $2, $3, $4)",
		metricName, value, unit, time.Now())
	return err
}

func AddCostHistory(resourceID string, cost float64, costType string) error {
	db, err := Connect()
	if err != nil {
		return err
	}
	_, err = db.Exec(context.Background(), "INSERT INTO cost_history (resource_id, cost, cost_type, currency, date) VALUES ($1, $2, $3, $4, $5)",
		resourceID, cost, costType, "USD", time.Now())
	return err
}

func AppendSignedActionLog(resourceID, actionType, details string) error {
	db, err := Connect()
	if err != nil {
		return err
	}

	ctx := context.Background()
	var previousHash string
	err = db.QueryRow(ctx, "SELECT signature FROM action_logs ORDER BY id DESC LIMIT 1").Scan(&previousHash)
	if err != nil && err != pgx.ErrNoRows {
		return err
	}
	if err == pgx.ErrNoRows {
		previousHash = "0000000000000000000000000000000000000000000000000000000000000000"
	}

	timestamp := time.Now().UTC()
	rawStr := fmt.Sprintf("%s|%s|%s|%s|%s", resourceID, actionType, details, timestamp.Format(time.RFC3339Nano), previousHash)
	hasher := sha256.New()
	hasher.Write([]byte(rawStr))
	signature := hex.EncodeToString(hasher.Sum(nil))

	_, err = db.Exec(ctx, "INSERT INTO action_logs (resource_id, action_type, status, details, previous_hash, signature, timestamp) VALUES ($1, $2, $3, $4, $5, $6, $7)",
		resourceID, actionType, "SUCCESS", details, previousHash, signature, timestamp)
	return err
}

func GetActiveCloudCredentials(provider string) (map[string]interface{}, error) {
	db, err := Connect()
	if err != nil {
		return nil, err
	}

	var creds map[string]interface{}
	err = db.QueryRow(context.Background(), "SELECT credentials FROM cloud_connections WHERE provider_type = $1 AND is_active = true LIMIT 1", provider).Scan(&creds)
	if err != nil {
		return nil, err
	}

	_ = AppendSignedActionLog("SYSTEM", "VAULT_READ", fmt.Sprintf("Authorized key read for provider: %s", provider))

	return creds, nil
}
