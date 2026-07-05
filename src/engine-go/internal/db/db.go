package db

import (
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	_ "github.com/mattn/go-sqlite3"
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
	State         string
	HourlyPrice   float64
}

var (
	pool *sql.DB
	once sync.Once
)

func Connect() (*sql.DB, error) {
	var err error
	once.Do(func() {
		dbURL := os.Getenv("DATABASE_URL")
		if dbURL == "" {
			configDir, e := os.UserConfigDir()
			if e == nil {
				dbURL = fmt.Sprintf("%s/CloudReaper/metadata.db", configDir)
				os.MkdirAll(fmt.Sprintf("%s/CloudReaper", configDir), 0755)
			} else {
				dbURL = "./metadata.db"
			}
		} else {
			dbURL = strings.TrimPrefix(dbURL, "sqlite:///")
		}
		pool, err = sql.Open("sqlite3", dbURL)
		if err == nil {
			err = pool.Ping()
		}
		if err == nil {
			// Configure connection pool for better stability
			// Use environment variables or sensible defaults
			maxOpenConns := 25
			maxIdleConns := 5
			connMaxLifetime := 5 * time.Minute

			if val := os.Getenv("DB_MAX_OPEN_CONNS"); val != "" {
				if intVal, err := strconv.Atoi(val); err == nil && intVal > 0 {
					maxOpenConns = intVal
				}
			}
			if val := os.Getenv("DB_MAX_IDLE_CONNS"); val != "" {
				if intVal, err := strconv.Atoi(val); err == nil && intVal >= 0 {
					maxIdleConns = intVal
				}
			}
			if val := os.Getenv("DB_CONN_MAX_LIFETIME_MINUTES"); val != "" {
				if intVal, err := strconv.Atoi(val); err == nil && intVal > 0 {
					connMaxLifetime = time.Duration(intVal) * time.Minute
				}
			}

			pool.SetMaxOpenConns(maxOpenConns)
			pool.SetMaxIdleConns(maxIdleConns)
			pool.SetConnMaxLifetime(connMaxLifetime)
		}
	})
	return pool, err
}

func UpsertResources(resources []Resource) error {
	db, err := Connect()
	if err != nil {
		return err
	}

	tx, err := db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()

	sqlStmt := `
		INSERT INTO resources (id, name, type, region, tags, active, is_protected, is_unallocated, last_seen)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
	stmt, err := tx.Prepare(sqlStmt)
	if err != nil {
		return err
	}
	defer stmt.Close()

	for _, r := range resources {
		tagsJSON, err := json.Marshal(r.Tags)
		if err != nil {
			return fmt.Errorf("error marshaling tags: %w", err)
		}
		_, err = stmt.Exec(r.ID, r.Name, r.Type, r.Region, string(tagsJSON), r.Active, r.IsProtected, r.IsUnallocated, r.LastSeen)
		if err != nil {
			return fmt.Errorf("error in batch exec: %w", err)
		}
	}

	return tx.Commit()
}

func CleanupInactiveResources(lastScanStart time.Time) error {
	db, err := Connect()
	if err != nil {
		return err
	}
	_, err = db.Exec("UPDATE resources SET active = false WHERE last_seen < ?", lastScanStart)
	return err
}

func AddBusinessMetric(metricName string, value float64, unit string) error {
	db, err := Connect()
	if err != nil {
		return err
	}
	_, err = db.Exec("INSERT INTO business_metrics (metric_name, value, unit, date) VALUES (?, ?, ?, ?)",
		metricName, value, unit, time.Now())
	return err
}

func AddCostHistory(resourceID string, cost float64, costType string) error {
	db, err := Connect()
	if err != nil {
		return err
	}
	_, err = db.Exec("INSERT INTO cost_history (resource_id, cost, cost_type, currency, date) VALUES (?, ?, ?, ?, ?)",
		resourceID, cost, costType, "USD", time.Now())
	return err
}

func AppendSignedActionLog(resourceID, actionType, details string) error {
	db, err := Connect()
	if err != nil {
		return err
	}

	var previousHash string
	err = db.QueryRow("SELECT signature FROM action_logs ORDER BY id DESC LIMIT 1").Scan(&previousHash)
	if err != nil && err != sql.ErrNoRows {
		return err
	}
	if err == sql.ErrNoRows {
		previousHash = "0000000000000000000000000000000000000000000000000000000000000000"
	}

	timestamp := time.Now().UTC()
	rawStr := fmt.Sprintf("%s|%s|%s|%s|%s", resourceID, actionType, details, timestamp.Format(time.RFC3339Nano), previousHash)
	hasher := sha256.New()
	hasher.Write([]byte(rawStr))
	signature := hex.EncodeToString(hasher.Sum(nil))

	_, err = db.Exec("INSERT INTO action_logs (resource_id, action_type, status, details, previous_hash, signature, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
		resourceID, actionType, "SUCCESS", details, previousHash, signature, timestamp)
	return err
}

func GetAllResources(database *sql.DB) ([]Resource, error) {
	rows, err := database.Query("SELECT id, name, type, region, tags, active, is_protected, is_unallocated, last_seen FROM resources")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var resources []Resource
	for rows.Next() {
		var r Resource
		var tagsJSON string
		err := rows.Scan(&r.ID, &r.Name, &r.Type, &r.Region, &tagsJSON, &r.Active, &r.IsProtected, &r.IsUnallocated, &r.LastSeen)
		if err != nil {
			return nil, err
		}

		// Parse tags JSON
		if tagsJSON != "" {
			if err := json.Unmarshal([]byte(tagsJSON), &r.Tags); err != nil {
				r.Tags = make(map[string]*string)
			}
		} else {
			r.Tags = make(map[string]*string)
		}

		// Set default values for new fields
		r.State = "unknown"
		if r.Active {
			r.State = "running"
		} else {
			r.State = "stopped"
		}
		r.HourlyPrice = 0.0

		resources = append(resources, r)
	}

	return resources, nil
}

func GetActiveCloudCredentials(provider string) (map[string]interface{}, error) {
	db, err := Connect()
	if err != nil {
		return nil, err
	}

	var credsJSON string
	err = db.QueryRow("SELECT credentials FROM cloud_connections WHERE provider_type = ? AND is_active = true LIMIT 1", provider).Scan(&credsJSON)
	if err != nil {
		return nil, err
	}

	var creds map[string]interface{}
	if err := json.Unmarshal([]byte(credsJSON), &creds); err != nil {
		return nil, err
	}

	_ = AppendSignedActionLog("SYSTEM", "VAULT_READ", fmt.Sprintf("Authorized key read for provider: %s", provider))

	return creds, nil
}
