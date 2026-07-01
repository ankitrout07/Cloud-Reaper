package db

import (
	"context"
	"database/sql"
	"fmt"
	"sync"
	"time"
)

// BatchDB provides concurrent database operations with connection pooling
type BatchDB struct {
	pool    *sql.DB
	workers int
	timeout time.Duration
	mu      sync.RWMutex
}

// QueryResult represents the result of a database query
type QueryResult struct {
	Query string
	Rows  *sql.Rows
	Error error
	Done  chan struct{}
}

// BatchInsertResult represents the result of a batch insert operation
type BatchInsertResult struct {
	SuccessCount int
	FailureCount int
	Errors       []error
	Duration     time.Duration
}

// NewBatchDB creates a new batch database handler
func NewBatchDB(driver, dsn string, workers int) (*BatchDB, error) {
	pool, err := sql.Open(driver, dsn)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	// Configure connection pool
	pool.SetMaxOpenConns(workers * 2)
	pool.SetMaxIdleConns(workers)
	pool.SetConnMaxLifetime(time.Hour)

	return &BatchDB{
		pool:    pool,
		workers: workers,
		timeout: 30 * time.Second,
	}, nil
}

// BatchInsertResources performs concurrent batch insert of resources
func (bdb *BatchDB) BatchInsertResources(ctx context.Context, resources []Resource) (*BatchInsertResult, error) {
	if len(resources) == 0 {
		return &BatchInsertResult{}, nil
	}

	startTime := time.Now()
	result := &BatchInsertResult{
		Errors: make([]error, 0),
	}

	// Prepare insert statement
	stmt, err := bdb.pool.PrepareContext(ctx, `
		INSERT INTO resources (resource_id, provider, resource_type, region, tags, cost, created_at)
		VALUES (?, ?, ?, ?, ?, ?, ?)
	`)
	if err != nil {
		return nil, fmt.Errorf("failed to prepare statement: %w", err)
	}
	defer stmt.Close()

	// Concurrent inserts using worker pool
	jobs := make(chan Resource, len(resources))
	results := make(chan error, len(resources))

	var wg sync.WaitGroup
	for i := 0; i < bdb.workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for resource := range jobs {
				_, err := stmt.ExecContext(ctx,
					resource.ResourceID,
					resource.Provider,
					resource.ResourceType,
					resource.Region,
					resource.Tags,
					resource.Cost,
					time.Now(),
				)
				results <- err
			}
		}()
	}

	// Send jobs
	for _, resource := range resources {
		jobs <- resource
	}
	close(jobs)

	// Wait for completion
	wg.Wait()
	close(results)

	// Collect results
	for err := range results {
		if err != nil {
			result.FailureCount++
			result.Errors = append(result.Errors, err)
		} else {
			result.SuccessCount++
		}
	}

	result.Duration = time.Since(startTime)
	return result, nil
}

// ParallelQuery executes multiple queries in parallel
func (bdb *BatchDB) ParallelQuery(ctx context.Context, queries []string) []QueryResult {
	results := make([]QueryResult, len(queries))

	var wg sync.WaitGroup
	for i, query := range queries {
		wg.Add(1)
		go func(idx int, q string) {
			defer wg.Done()

			ctx, cancel := context.WithTimeout(ctx, bdb.timeout)
			defer cancel()

			rows, err := bdb.pool.QueryContext(ctx, q)
			results[idx] = QueryResult{
				Query: q,
				Rows:  rows,
				Error: err,
				Done:  make(chan struct{}),
			}
		}(i, query)
	}

	wg.Wait()
	return results
}

// BatchUpdate performs concurrent batch updates
func (bdb *BatchDB) BatchUpdate(ctx context.Context, table string, updates map[string]interface{}, whereClause string) (*BatchInsertResult, error) {
	startTime := time.Now()
	result := &BatchInsertResult{
		Errors: make([]error, 0),
	}

	// Build update query
	setClause := ""
	args := make([]interface{}, 0)
	i := 1
	for col, val := range updates {
		if i > 1 {
			setClause += ", "
		}
		setClause += fmt.Sprintf("%s = $%d", col, i)
		args = append(args, val)
		i++
	}

	query := fmt.Sprintf("UPDATE %s SET %s WHERE %s", table, setClause, whereClause)

	// Execute update
	_, err := bdb.pool.ExecContext(ctx, query, args...)
	if err != nil {
		result.FailureCount++
		result.Errors = append(result.Errors, err)
	} else {
		result.SuccessCount++
	}

	result.Duration = time.Since(startTime)
	return result, nil
}

// GetPoolStats returns connection pool statistics
func (bdb *BatchDB) GetPoolStats() sql.DBStats {
	return bdb.pool.Stats()
}

// Close closes the database connection pool
func (bdb *BatchDB) Close() error {
	return bdb.pool.Close()
}

// Ping checks database connectivity
func (bdb *BatchDB) Ping(ctx context.Context) error {
	return bdb.pool.PingContext(ctx)
}

// TransactionManager manages database transactions
type TransactionManager struct {
	db *BatchDB
}

// NewTransactionManager creates a new transaction manager
func NewTransactionManager(db *BatchDB) *TransactionManager {
	return &TransactionManager{db: db}
}

// ExecuteInTransaction executes a function within a transaction
func (tm *TransactionManager) ExecuteInTransaction(ctx context.Context, fn func(*sql.Tx) error) error {
	tx, err := tm.db.pool.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}

	defer func() {
		if p := recover(); p != nil {
			tx.Rollback()
			panic(p) // re-throw panic after rollback
		}
	}()

	if err := fn(tx); err != nil {
		if rbErr := tx.Rollback(); rbErr != nil {
			return fmt.Errorf("transaction failed: %v, rollback failed: %w", err, rbErr)
		}
		return err
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("failed to commit transaction: %w", err)
	}

	return nil
}

// Resource represents a cloud resource for database operations
type Resource struct {
	ResourceID   string
	Provider     string
	ResourceType string
	Region       string
	Tags         string // JSON string
	Cost         float64
	CreatedAt    time.Time
}

// QueryBuilder helps build complex SQL queries
type QueryBuilder struct {
	selectClause string
	fromClause   string
	whereClause  string
	groupClause  string
	orderClause  string
	limitClause  string
	args         []interface{}
	argIndex     int
}

// NewQueryBuilder creates a new query builder
func NewQueryBuilder() *QueryBuilder {
	return &QueryBuilder{
		args:     make([]interface{}, 0),
		argIndex: 1,
	}
}

// Select adds SELECT clause
func (qb *QueryBuilder) Select(columns string) *QueryBuilder {
	qb.selectClause = "SELECT " + columns
	return qb
}

// From adds FROM clause
func (qb *QueryBuilder) From(table string) *QueryBuilder {
	qb.fromClause = " FROM " + table
	return qb
}

// Where adds WHERE clause
func (qb *QueryBuilder) Where(condition string, args ...interface{}) *QueryBuilder {
	if qb.whereClause == "" {
		qb.whereClause = " WHERE " + condition
	} else {
		qb.whereClause += " AND " + condition
	}
	qb.args = append(qb.args, args...)
	return qb
}

// GroupBy adds GROUP BY clause
func (qb *QueryBuilder) GroupBy(columns string) *QueryBuilder {
	qb.groupClause = " GROUP BY " + columns
	return qb
}

// OrderBy adds ORDER BY clause
func (qb *QueryBuilder) OrderBy(columns string) *QueryBuilder {
	qb.orderClause = " ORDER BY " + columns
	return qb
}

// Limit adds LIMIT clause
func (qb *QueryBuilder) Limit(limit int) *QueryBuilder {
	qb.limitClause = fmt.Sprintf(" LIMIT %d", limit)
	return qb
}

// Build builds the final query string
func (qb *QueryBuilder) Build() (string, []interface{}) {
	query := qb.selectClause + qb.fromClause + qb.whereClause + qb.groupClause + qb.orderClause + qb.limitClause
	return query, qb.args
}

// IndexManager manages database indexes
type IndexManager struct {
	db *BatchDB
}

// NewIndexManager creates a new index manager
func NewIndexManager(db *BatchDB) *IndexManager {
	return &IndexManager{db: db}
}

// CreateIndex creates a database index
func (im *IndexManager) CreateIndex(ctx context.Context, table, indexName, columns string, unique bool) error {
	uniqueStr := ""
	if unique {
		uniqueStr = " UNIQUE"
	}

	query := fmt.Sprintf("CREATE%s INDEX IF NOT EXISTS %s ON %s (%s)", uniqueStr, indexName, table, columns)
	_, err := im.db.pool.ExecContext(ctx, query)
	return err
}

// DropIndex drops a database index
func (im *IndexManager) DropIndex(ctx context.Context, indexName string) error {
	query := fmt.Sprintf("DROP INDEX IF EXISTS %s", indexName)
	_, err := im.db.pool.ExecContext(ctx, query)
	return err
}

// ListIndexes lists all indexes for a table
func (im *IndexManager) ListIndexes(ctx context.Context, table string) ([]string, error) {
	query := fmt.Sprintf("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='%s'", table)
	rows, err := im.db.pool.QueryContext(ctx, query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var indexes []string
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return nil, err
		}
		indexes = append(indexes, name)
	}

	return indexes, nil
}
