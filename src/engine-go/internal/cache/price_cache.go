package cache

import (
	"sync"
	"time"
)

// LRUCache implements a thread-safe LRU (Least Recently Used) cache
type LRUCache struct {
	capacity int
	items    map[string]*cacheItem
	head     *cacheItem
	tail     *cacheItem
	mu       sync.RWMutex
	ttl      time.Duration
}

// cacheItem represents an item in the cache
type cacheItem struct {
	key       string
	value     interface{}
	prev      *cacheItem
	next      *cacheItem
	expiresAt time.Time
}

// PriceCache provides LRU caching for price lookups with TTL
type PriceCache struct {
	lru    *LRUCache
	misses int64
	hits   int64
	mu     sync.RWMutex
}

// PriceCacheConfig holds configuration for the price cache
type PriceCacheConfig struct {
	Capacity int
	TTL      time.Duration
}

// DefaultPriceCacheConfig returns sensible defaults
func DefaultPriceCacheConfig() PriceCacheConfig {
	return PriceCacheConfig{
		Capacity: 10000,
		TTL:      15 * time.Minute,
	}
}

// NewLRUCache creates a new LRU cache
func NewLRUCache(capacity int, ttl time.Duration) *LRUCache {
	cache := &LRUCache{
		capacity: capacity,
		items:    make(map[string]*cacheItem),
		ttl:      ttl,
	}

	// Initialize head and tail dummy nodes
	head := &cacheItem{}
	tail := &cacheItem{}
	head.next = tail
	tail.prev = head
	cache.head = head
	cache.tail = tail

	return cache
}

// NewPriceCache creates a new price cache
func NewPriceCache(config PriceCacheConfig) *PriceCache {
	if config.Capacity == 0 {
		config = DefaultPriceCacheConfig()
	}

	return &PriceCache{
		lru: NewLRUCache(config.Capacity, config.TTL),
	}
}

// Get retrieves a value from the cache
func (pc *PriceCache) Get(key string) (interface{}, bool) {
	value, found := pc.lru.Get(key)

	pc.mu.Lock()
	defer pc.mu.Unlock()

	if found {
		pc.hits++
	} else {
		pc.misses++
	}

	return value, found
}

// GetOrFetch retrieves a value from cache or fetches it using the provided function
func (pc *PriceCache) GetOrFetch(key string, fetchFunc func() (interface{}, error)) (interface{}, error) {
	// Try cache first
	if value, found := pc.Get(key); found {
		return value, nil
	}

	// Fetch the value
	value, err := fetchFunc()
	if err != nil {
		return nil, err
	}

	// Store in cache
	pc.Put(key, value)
	return value, nil
}

// Put stores a value in the cache
func (pc *PriceCache) Put(key string, value interface{}) {
	pc.lru.Put(key, value)
}

// Delete removes a value from the cache
func (pc *PriceCache) Delete(key string) {
	pc.lru.Delete(key)
}

// Clear removes all items from the cache
func (pc *PriceCache) Clear() {
	pc.lru.Clear()
}

// GetStats returns cache statistics
func (pc *PriceCache) GetStats() CacheStats {
	pc.mu.RLock()
	defer pc.mu.RUnlock()

	totalRequests := pc.hits + pc.misses
	hitRate := 0.0
	if totalRequests > 0 {
		hitRate = float64(pc.hits) / float64(totalRequests)
	}

	return CacheStats{
		Hits:     pc.hits,
		Misses:   pc.misses,
		HitRate:  hitRate,
		Size:     pc.lru.Size(),
		Capacity: pc.lru.Capacity(),
	}
}

// CacheStats represents cache statistics
type CacheStats struct {
	Hits     int64
	Misses   int64
	HitRate  float64
	Size     int
	Capacity int
}

// Get retrieves a value from the LRU cache
func (lc *LRUCache) Get(key string) (interface{}, bool) {
	lc.mu.Lock()
	defer lc.mu.Unlock()

	item, exists := lc.items[key]
	if !exists {
		return nil, false
	}

	// Check if expired
	if lc.ttl > 0 && time.Now().After(item.expiresAt) {
		lc.removeItem(item)
		delete(lc.items, key)
		return nil, false
	}

	// Move to front (most recently used)
	lc.moveToFront(item)
	return item.value, true
}

// Put stores a value in the LRU cache
func (lc *LRUCache) Put(key string, value interface{}) {
	lc.mu.Lock()
	defer lc.mu.Unlock()

	// Check if key already exists
	if item, exists := lc.items[key]; exists {
		item.value = value
		item.expiresAt = time.Now().Add(lc.ttl)
		lc.moveToFront(item)
		return
	}

	// Create new item
	item := &cacheItem{
		key:       key,
		value:     value,
		expiresAt: time.Now().Add(lc.ttl),
	}

	lc.items[key] = item
	lc.addToFront(item)

	// Check if capacity exceeded
	if len(lc.items) > lc.capacity {
		lc.removeOldest()
	}
}

// Delete removes a value from the cache
func (lc *LRUCache) Delete(key string) {
	lc.mu.Lock()
	defer lc.mu.Unlock()

	if item, exists := lc.items[key]; exists {
		lc.removeItem(item)
		delete(lc.items, key)
	}
}

// Clear removes all items from the cache
func (lc *LRUCache) Clear() {
	lc.mu.Lock()
	defer lc.mu.Unlock()

	lc.items = make(map[string]*cacheItem)
	lc.head.next = lc.tail
	lc.tail.prev = lc.head
}

// Size returns the current number of items in the cache
func (lc *LRUCache) Size() int {
	lc.mu.RLock()
	defer lc.mu.RUnlock()
	return len(lc.items)
}

// Capacity returns the cache capacity
func (lc *LRUCache) Capacity() int {
	return lc.capacity
}

// addToFront adds an item to the front of the list
func (lc *LRUCache) addToFront(item *cacheItem) {
	item.next = lc.head.next
	item.prev = lc.head
	lc.head.next.prev = item
	lc.head.next = item
}

// removeItem removes an item from the list
func (lc *LRUCache) removeItem(item *cacheItem) {
	item.prev.next = item.next
	item.next.prev = item.prev
}

// moveToFront moves an item to the front of the list
func (lc *LRUCache) moveToFront(item *cacheItem) {
	lc.removeItem(item)
	lc.addToFront(item)
}

// removeOldest removes the oldest item from the cache
func (lc *LRUCache) removeOldest() {
	if lc.tail.prev == lc.head {
		return
	}

	oldest := lc.tail.prev
	lc.removeItem(oldest)
	delete(lc.items, oldest.key)
}

// CleanupExpired removes all expired items from the cache
func (lc *LRUCache) CleanupExpired() {
	lc.mu.Lock()
	defer lc.mu.Unlock()

	now := time.Now()
	for key, item := range lc.items {
		if lc.ttl > 0 && now.After(item.expiresAt) {
			lc.removeItem(item)
			delete(lc.items, key)
		}
	}
}

// StartCleanupRoutine starts a background routine to clean up expired items
func (pc *PriceCache) StartCleanupRoutine(interval time.Duration) {
	ticker := time.NewTicker(interval)
	go func() {
		for range ticker.C {
			pc.lru.CleanupExpired()
		}
	}()
}

// MultiLevelCache implements a multi-level cache (memory + optional persistent)
type MultiLevelCache struct {
	l1 *PriceCache // Memory cache
	l2 *PriceCache // Optional second level cache
}

// NewMultiLevelCache creates a new multi-level cache
func NewMultiLevelCache(l1Config, l2Config PriceCacheConfig) *MultiLevelCache {
	cache := &MultiLevelCache{
		l1: NewPriceCache(l1Config),
	}

	if l2Config.Capacity > 0 {
		cache.l2 = NewPriceCache(l2Config)
	}

	return cache
}

// Get retrieves a value from the multi-level cache
func (mlc *MultiLevelCache) Get(key string) (interface{}, bool) {
	// Try L1 first
	if value, found := mlc.l1.Get(key); found {
		return value, true
	}

	// Try L2 if available
	if mlc.l2 != nil {
		if value, found := mlc.l2.Get(key); found {
			// Promote to L1
			mlc.l1.Put(key, value)
			return value, true
		}
	}

	return nil, false
}

// Put stores a value in both cache levels
func (mlc *MultiLevelCache) Put(key string, value interface{}) {
	mlc.l1.Put(key, value)
	if mlc.l2 != nil {
		mlc.l2.Put(key, value)
	}
}

// GetCombinedStats returns combined statistics from all cache levels
func (mlc *MultiLevelCache) GetCombinedStats() map[string]CacheStats {
	stats := make(map[string]CacheStats)
	stats["l1"] = mlc.l1.GetStats()

	if mlc.l2 != nil {
		stats["l2"] = mlc.l2.GetStats()
	}

	return stats
}
