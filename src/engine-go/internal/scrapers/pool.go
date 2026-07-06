package scrapers

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"cloud-reaper/engine-go/internal/ratelimiter"
)

// ScrapingJob represents a single scraping task
type ScrapingJob struct {
	Provider     string            // azure, aws, gcp
	ResourceType string            // compute, storage, network
	Region       string            // region to scrape
	Params       map[string]string // additional parameters
}

// ScrapingResult represents the result of a scraping job
type ScrapingResult struct {
	Job       ScrapingJob
	Data      interface{}
	Error     error
	Duration  time.Duration
	Timestamp time.Time
}

// ScrapingPool manages concurrent scraping operations
type ScrapingPool struct {
	workers     int
	jobQueue    chan ScrapingJob
	results     chan ScrapingResult
	rateLimiter *ratelimiter.TokenBucketRateLimiter
	workerWg    sync.WaitGroup
	ctx         context.Context
	cancel      context.CancelFunc
	scrapers    map[string]Scraper
	scrapersMu  sync.RWMutex
	stats       PoolStats
	statsMu     sync.RWMutex
}

// Scraper interface for cloud provider scrapers
type Scraper interface {
	Scrape(ctx context.Context, job ScrapingJob) (interface{}, error)
	Name() string
}

// PoolStats tracks scraping pool statistics
type PoolStats struct {
	JobsSubmitted   int64
	JobsCompleted   int64
	JobsFailed      int64
	TotalDuration   time.Duration
	AverageDuration time.Duration
	ActiveWorkers   int
}

// PoolConfig holds configuration for the scraping pool
type PoolConfig struct {
	Workers         int
	QueueSize       int
	RateLimit       float64 // requests per second
	EnableRateLimit bool
}

// DefaultPoolConfig returns sensible defaults
func DefaultPoolConfig() PoolConfig {
	return PoolConfig{
		Workers:         10,
		QueueSize:       1000,
		RateLimit:       100.0,
		EnableRateLimit: true,
	}
}

// NewScrapingPool creates a new scraping pool
func NewScrapingPool(config PoolConfig) *ScrapingPool {
	if config.Workers == 0 {
		config = DefaultPoolConfig()
	}

	ctx, cancel := context.WithCancel(context.Background())

	pool := &ScrapingPool{
		workers:     config.Workers,
		jobQueue:    make(chan ScrapingJob, config.QueueSize),
		results:     make(chan ScrapingResult, config.QueueSize),
		ctx:         ctx,
		cancel:      cancel,
		scrapers:    make(map[string]Scraper),
		rateLimiter: ratelimiter.NewTokenBucketRateLimiter(config.RateLimit, int(config.RateLimit)),
	}

	// Start workers
	pool.startWorkers()

	return pool
}

// RegisterScraper registers a scraper for a provider
func (sp *ScrapingPool) RegisterScraper(provider string, scraper Scraper) {
	sp.scrapersMu.Lock()
	defer sp.scrapersMu.Unlock()
	sp.scrapers[provider] = scraper
}

// startWorkers starts the worker goroutines
func (sp *ScrapingPool) startWorkers() {
	for i := 0; i < sp.workers; i++ {
		sp.workerWg.Add(1)
		go sp.worker(i)
	}
}

// worker processes scraping jobs
func (sp *ScrapingPool) worker(id int) {
	defer sp.workerWg.Done()

	for {
		select {
		case <-sp.ctx.Done():
			return
		case job := <-sp.jobQueue:
			sp.processJob(job)
		}
	}
}

// processJob processes a single scraping job
func (sp *ScrapingPool) processJob(job ScrapingJob) {
	sp.statsMu.Lock()
	sp.stats.ActiveWorkers++
	sp.statsMu.Unlock()

	startTime := time.Now()

	// Rate limiting
	if sp.rateLimiter != nil {
		sp.rateLimiter.Wait(sp.ctx)
	}

	// Get scraper for provider
	sp.scrapersMu.RLock()
	scraper, ok := sp.scrapers[job.Provider]
	sp.scrapersMu.RUnlock()

	var result ScrapingResult
	result.Job = job
	result.Timestamp = time.Now()

	if !ok {
		result.Error = fmt.Errorf("no scraper registered for provider: %s", job.Provider)
	} else {
		data, err := scraper.Scrape(sp.ctx, job)
		result.Data = data
		result.Error = err
	}

	result.Duration = time.Since(startTime)

	// Update stats
	sp.statsMu.Lock()
	sp.stats.JobsCompleted++
	if result.Error != nil {
		sp.stats.JobsFailed++
	}
	sp.stats.TotalDuration += result.Duration
	if sp.stats.JobsCompleted > 0 {
		sp.stats.AverageDuration = sp.stats.TotalDuration / time.Duration(sp.stats.JobsCompleted)
	}
	sp.stats.ActiveWorkers--
	sp.statsMu.Unlock()

	// Send result
	select {
	case sp.results <- result:
	case <-sp.ctx.Done():
	}
}

// SubmitJob submits a scraping job to the pool
func (sp *ScrapingPool) SubmitJob(job ScrapingJob) error {
	sp.statsMu.Lock()
	sp.stats.JobsSubmitted++
	sp.statsMu.Unlock()

	select {
	case sp.jobQueue <- job:
		return nil
	case <-sp.ctx.Done():
		return fmt.Errorf("pool is shutting down")
	default:
		return fmt.Errorf("job queue is full")
	}
}

// SubmitJobs submits multiple scraping jobs
func (sp *ScrapingPool) SubmitJobs(jobs []ScrapingJob) error {
	for _, job := range jobs {
		if err := sp.SubmitJob(job); err != nil {
			return err
		}
	}
	return nil
}

// GetResult retrieves a scraping result
func (sp *ScrapingPool) GetResult() (ScrapingResult, error) {
	select {
	case result := <-sp.results:
		return result, nil
	case <-sp.ctx.Done():
		return ScrapingResult{}, fmt.Errorf("pool is shutting down")
	}
}

// GetResults retrieves multiple scraping results
func (sp *ScrapingPool) GetResults(count int) []ScrapingResult {
	results := make([]ScrapingResult, 0, count)
	for i := 0; i < count; i++ {
		result, err := sp.GetResult()
		if err != nil {
			break
		}
		results = append(results, result)
	}
	return results
}

// ScrapeAllProviders scrapes all providers concurrently
func (sp *ScrapingPool) ScrapeAllProviders(regions []string, resourceTypes []string) map[string]interface{} {
	// Create jobs for all provider/region/resource combinations
	var jobs []ScrapingJob
	providers := []string{"azure", "aws", "gcp"}

	for _, provider := range providers {
		for _, region := range regions {
			for _, resourceType := range resourceTypes {
				jobs = append(jobs, ScrapingJob{
					Provider:     provider,
					Region:       region,
					ResourceType: resourceType,
					Params:       make(map[string]string),
				})
			}
		}
	}

	// Submit all jobs
	sp.SubmitJobs(jobs)

	// Collect results
	results := make(map[string]interface{})
	for i := 0; i < len(jobs); i++ {
		result := <-sp.results
		if result.Error != nil {
			fmt.Printf("Scraping error for %s/%s: %v\n", result.Job.Provider, result.Job.Region, result.Error)
			continue
		}
		key := fmt.Sprintf("%s_%s_%s", result.Job.Provider, result.Job.Region, result.Job.ResourceType)
		results[key] = result.Data
	}

	return results
}

// GetStats returns pool statistics
func (sp *ScrapingPool) GetStats() PoolStats {
	sp.statsMu.RLock()
	defer sp.statsMu.RUnlock()
	return sp.stats
}

// Stop gracefully stops the scraping pool
func (sp *ScrapingPool) Stop() {
	sp.cancel()
	sp.workerWg.Wait()
	close(sp.jobQueue)
	close(sp.results)
}

// ToJSON converts stats to JSON
func (ps PoolStats) ToJSON() (string, error) {
	data, err := json.Marshal(ps)
	if err != nil {
		return "", err
	}
	return string(data), nil
}
