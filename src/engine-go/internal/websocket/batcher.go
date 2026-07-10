package websocket

import (
	"encoding/json"
	"fmt"
	"sync"
	"time"
)

// Message represents a WebSocket message to be batched
type Message struct {
	Event  string                 `json:"event"`
	Data   map[string]interface{} `json:"data"`
	Room   string                 `json:"room,omitempty"`
	SentAt time.Time              `json:"sent_at"`
}

// Batch represents a collection of messages to be sent together
type Batch struct {
	Event    string    `json:"event"`
	Messages []Message `json:"messages"`
	Count    int       `json:"count"`
	SentAt   time.Time `json:"sent_at"`
	Room     string    `json:"room,omitempty"`
}

// BatcherConfig holds configuration for the WebSocket batcher
type BatcherConfig struct {
	BatchInterval       time.Duration // Time to wait before flushing a batch
	MaxBatchSize        int           // Maximum messages per batch
	MaxQueueSize        int           // Maximum messages in queue before dropping
	FlushOnShutdown     bool          // Whether to flush all batches on shutdown
	EnableCompression   bool          // Whether to enable message compression
	AdaptiveBatching    bool          // Whether to enable adaptive batching based on load
	MaxConcurrentFlush  int           // Maximum concurrent flush operations
	BufferPoolSize      int           // Size of buffer pool for memory optimization
}

// DefaultBatcherConfig returns sensible defaults
func DefaultBatcherConfig() BatcherConfig {
	return BatcherConfig{
		BatchInterval:      150 * time.Millisecond,
		MaxBatchSize:       30,
		MaxQueueSize:       1000,
		FlushOnShutdown:    true,
		EnableCompression:  true,
		AdaptiveBatching:   true,
		MaxConcurrentFlush: 10,
		BufferPoolSize:     100,
	}
}

// WebSocketBatcher batches WebSocket messages to reduce network overhead
type WebSocketBatcher struct {
	config            BatcherConfig
	batches           map[string][]Message // event -> messages
	timers            map[string]*time.Timer
	mu                sync.RWMutex
	emitter           MessageEmitter
	compressor        *MessageCompressor
	metricsBroadcaster *MetricsBroadcaster
	running           bool
	stopChan          chan struct{}
	wg                sync.WaitGroup
	droppedCount      int64
	sentCount         int64
	flushSemaphore    chan struct{}
	bufferPool        *sync.Pool
	loadMonitor       *loadMonitor
}

// MessageEmitter is the interface for sending batches
type MessageEmitter interface {
	Emit(event string, data interface{}) error
	EmitToRoom(event string, room string, data interface{}) error
}

// loadMonitor tracks system load for adaptive batching
type loadMonitor struct {
	messageCount int64
	windowStart  time.Time
	mu           sync.Mutex
	windowSize   time.Duration
}

func newLoadMonitor(windowSize time.Duration) *loadMonitor {
	return &loadMonitor{
		windowStart: time.Now(),
		windowSize:  windowSize,
	}
}

func (lm *loadMonitor) recordMessage() {
	lm.mu.Lock()
	defer lm.mu.Unlock()
	lm.messageCount++
}

func (lm *loadMonitor) getMessagesPerSecond() float64 {
	lm.mu.Lock()
	defer lm.mu.Unlock()

	elapsed := time.Since(lm.windowStart)
	if elapsed < lm.windowSize {
		return float64(lm.messageCount) / elapsed.Seconds()
	}

	// Reset window if expired
	rate := float64(lm.messageCount) / elapsed.Seconds()
	lm.messageCount = 0
	lm.windowStart = time.Now()
	return rate
}

// NewWebSocketBatcher creates a new WebSocket batcher
func NewWebSocketBatcher(emitter MessageEmitter, config BatcherConfig) *WebSocketBatcher {
	if config.BatchInterval == 0 {
		config = DefaultBatcherConfig()
	}

	if config.MaxConcurrentFlush <= 0 {
		config.MaxConcurrentFlush = 10
	}

	if config.BufferPoolSize <= 0 {
		config.BufferPoolSize = 100
	}

	batcher := &WebSocketBatcher{
		config:      config,
		batches:     make(map[string][]Message),
		timers:      make(map[string]*time.Timer),
		emitter:     emitter,
		running:     true,
		stopChan:    make(chan struct{}),
		flushSemaphore: make(chan struct{}, config.MaxConcurrentFlush),
		bufferPool: &sync.Pool{
			New: func() interface{} {
				return make([]Message, 0, config.MaxBatchSize)
			},
		},
		loadMonitor: newLoadMonitor(time.Second),
	}

	// Initialize compressor if enabled
	if config.EnableCompression {
		batcher.compressor = NewMessageCompressor(DefaultCompressorConfig())
	}

	return batcher
}

// SetMetricsBroadcaster sets the metrics broadcaster for real-time broadcasting
func (wb *WebSocketBatcher) SetMetricsBroadcaster(broadcaster *MetricsBroadcaster) {
	wb.mu.Lock()
	defer wb.mu.Unlock()
	wb.metricsBroadcaster = broadcaster
}

// Emit queues a message for batched emission
func (wb *WebSocketBatcher) Emit(event string, data map[string]interface{}, room string) error {
	if !wb.running {
		return fmt.Errorf("batcher is not running")
	}

	wb.loadMonitor.recordMessage()

	// Get adaptive parameters before locking mutex
	adaptiveBatchSize := wb.config.MaxBatchSize
	adaptiveInterval := wb.config.BatchInterval
	if wb.config.AdaptiveBatching {
		messagesPerSecond := wb.loadMonitor.getMessagesPerSecond()
		if messagesPerSecond > 1000 {
			// High load: increase batch size and interval
			adaptiveBatchSize = min(wb.config.MaxBatchSize*2, 100)
			adaptiveInterval = wb.config.BatchInterval * 2
		} else if messagesPerSecond < 100 {
			// Low load: decrease batch size and interval for lower latency
			adaptiveBatchSize = max(wb.config.MaxBatchSize/2, 10)
			adaptiveInterval = wb.config.BatchInterval / 2
		}
	}

	wb.mu.Lock()
	defer wb.mu.Unlock()

	// Check queue size
	totalQueued := 0
	for _, msgs := range wb.batches {
		totalQueued += len(msgs)
	}

	if totalQueued >= wb.config.MaxQueueSize {
		wb.droppedCount++
		return fmt.Errorf("queue is full, message dropped")
	}

	// Create message
	msg := Message{
		Event:  event,
		Data:   data,
		Room:   room,
		SentAt: time.Now(),
	}

	// Add to batch
	wb.batches[event] = append(wb.batches[event], msg)

	// Check if we should flush immediately
	if len(wb.batches[event]) >= adaptiveBatchSize {
		go wb.flushBatch(event, room)
		return nil
	}

	// Set/reset timer for this event (mutex already held)
	if timer, exists := wb.timers[event]; exists {
		timer.Stop()
	}

	wb.timers[event] = time.AfterFunc(adaptiveInterval, func() {
		wb.flushBatch(event, room)
	})

	// Auto-broadcast metrics updates to WebSocket clients (outside mutex)
	if wb.metricsBroadcaster != nil && event == "metric_update" {
		// Create a copy of data to avoid race conditions
		dataCopy := make(map[string]interface{})
		for k, v := range data {
			dataCopy[k] = v
		}

		go func() {
			defer func() {
				if r := recover(); r != nil {
					fmt.Printf("[WebSocket Batcher] Panic recovered in broadcast: %v\n", r)
				}
			}()

			if value, ok := dataCopy["value"].(float64); ok {
				if timeStr, ok := dataCopy["time"].(string); ok {
					metadata := make(map[string]interface{})
					for k, v := range dataCopy {
						if k != "value" && k != "time" {
							metadata[k] = v
						}
					}
					if room != "" {
						wb.metricsBroadcaster.BroadcastToRoom(room, timeStr, value, metadata)
					} else {
						wb.metricsBroadcaster.Broadcast(timeStr, value, metadata)
					}
				}
			}
		}()
	}

	return nil
}

// flushBatch sends all pending messages for an event
func (wb *WebSocketBatcher) flushBatch(event string, room string) {
	defer func() {
		if r := recover(); r != nil {
			fmt.Printf("[WebSocket Batcher] Panic recovered in flushBatch: %v\n", r)
		}
	}()

	// Acquire semaphore to limit concurrent flushes
	wb.flushSemaphore <- struct{}{}
	defer func() { <-wb.flushSemaphore }()

	wb.mu.Lock()
	messages, ok := wb.batches[event]
	if !ok || len(messages) == 0 {
		wb.mu.Unlock()
		return
	}

	// Clear the batch
	delete(wb.batches, event)
	delete(wb.timers, event)
	wb.mu.Unlock()

	// Create batch
	batch := Batch{
		Event:    fmt.Sprintf("%s_batch", event),
		Messages: messages,
		Count:    len(messages),
		SentAt:   time.Now(),
		Room:     room,
	}

	// Compress batch if enabled
	payload := interface{}(batch)
	if wb.compressor != nil {
		compressedBatch, err := wb.compressor.CompressBatch(batch)
		if err == nil {
			payload = compressedBatch
		} else {
			fmt.Printf("[WebSocket Batcher] Compression error, using uncompressed: %v\n", err)
		}
	}

	// Send the batch
	var err error
	if room != "" {
		err = wb.emitter.EmitToRoom(batch.Event, room, payload)
	} else {
		err = wb.emitter.Emit(batch.Event, payload)
	}

	if err != nil {
		fmt.Printf("[WebSocket Batcher] Error emitting batch: %v\n", err)
	} else {
		wb.mu.Lock()
		wb.sentCount += int64(len(messages))
		wb.mu.Unlock()
	}
}

// FlushAll immediately sends all pending batches
func (wb *WebSocketBatcher) FlushAll() error {
	defer func() {
		if r := recover(); r != nil {
			fmt.Printf("[WebSocket Batcher] Panic recovered in FlushAll: %v\n", r)
		}
	}()

	wb.mu.RLock()
	events := make([]string, 0, len(wb.batches))
	for event := range wb.batches {
		events = append(events, event)
	}
	wb.mu.RUnlock()

	var lastErr error
	for _, event := range events {
		wb.flushBatch(event, "") // Flush without specific room
	}

	return lastErr
}

// Stop gracefully stops the batcher
func (wb *WebSocketBatcher) Stop() {
	defer func() {
		if r := recover(); r != nil {
			fmt.Printf("[WebSocket Batcher] Panic recovered in Stop: %v\n", r)
		}
	}()

	wb.mu.Lock()
	if !wb.running {
		wb.mu.Unlock()
		return
	}
	wb.running = false
	wb.mu.Unlock()

	// Flush all pending batches if configured
	if wb.config.FlushOnShutdown {
		wb.FlushAll()
	}

	// Stop all timers safely
	wb.mu.Lock()
	for _, timer := range wb.timers {
		timer.Stop()
	}
	wb.timers = make(map[string]*time.Timer)
	wb.mu.Unlock()

	// Signal stop
	close(wb.stopChan)
	wb.wg.Wait()
}

// GetStatistics returns batcher statistics
func (wb *WebSocketBatcher) GetStatistics() map[string]interface{} {
	wb.mu.RLock()
	defer wb.mu.RUnlock()

	totalQueued := 0
	for _, msgs := range wb.batches {
		totalQueued += len(msgs)
	}

	stats := map[string]interface{}{
		"running":                  wb.running,
		"total_queued":             totalQueued,
		"dropped_count":            wb.droppedCount,
		"sent_count":               wb.sentCount,
		"batch_count":              len(wb.batches),
		"batch_interval_ms":        wb.config.BatchInterval.Milliseconds(),
		"max_batch_size":           wb.config.MaxBatchSize,
		"max_queue_size":           wb.config.MaxQueueSize,
		"enable_compression":       wb.config.EnableCompression,
		"adaptive_batching":        wb.config.AdaptiveBatching,
		"max_concurrent_flush":    wb.config.MaxConcurrentFlush,
		"buffer_pool_size":         wb.config.BufferPoolSize,
		"messages_per_second":     wb.loadMonitor.getMessagesPerSecond(),
	}

	// Add compression stats if available
	if wb.compressor != nil {
		compressionStats := wb.compressor.GetStats()
		stats["compression"] = map[string]interface{}{
			"total_messages":     compressionStats.TotalMessages,
			"compressed_size":     compressionStats.CompressedSize,
			"original_size":       compressionStats.OriginalSize,
			"compression_ratio":   compressionStats.CompressionRatio,
			"total_savings":       compressionStats.TotalSavings,
		}
	}

	return stats
}

// Helper functions for adaptive batching
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

// ToJSON converts statistics to JSON
func (wb *WebSocketBatcher) ToJSON() (string, error) {
	stats := wb.GetStatistics()
	data, err := json.Marshal(stats)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

// MockEmitter is a mock implementation of MessageEmitter for testing
type MockEmitter struct {
	messages []map[string]interface{}
	mu       sync.Mutex
}

func NewMockEmitter() *MockEmitter {
	return &MockEmitter{
		messages: make([]map[string]interface{}, 0),
	}
}

func (me *MockEmitter) Emit(event string, data interface{}) error {
	me.mu.Lock()
	defer me.mu.Unlock()

	msg := map[string]interface{}{
		"event": event,
		"data":  data,
	}
	me.messages = append(me.messages, msg)
	return nil
}

func (me *MockEmitter) EmitToRoom(event string, room string, data interface{}) error {
	me.mu.Lock()
	defer me.mu.Unlock()

	msg := map[string]interface{}{
		"event": event,
		"room":  room,
		"data":  data,
	}
	me.messages = append(me.messages, msg)
	return nil
}

func (me *MockEmitter) GetMessages() []map[string]interface{} {
	me.mu.Lock()
	defer me.mu.Unlock()

	result := make([]map[string]interface{}, len(me.messages))
	copy(result, me.messages)
	return result
}

func (me *MockEmitter) Clear() {
	me.mu.Lock()
	defer me.mu.Unlock()
	me.messages = make([]map[string]interface{}, 0)
}
