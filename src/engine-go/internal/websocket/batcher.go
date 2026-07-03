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
	BatchInterval   time.Duration // Time to wait before flushing a batch
	MaxBatchSize    int           // Maximum messages per batch
	MaxQueueSize    int           // Maximum messages in queue before dropping
	FlushOnShutdown bool          // Whether to flush all batches on shutdown
}

// DefaultBatcherConfig returns sensible defaults
func DefaultBatcherConfig() BatcherConfig {
	return BatcherConfig{
		BatchInterval:   150 * time.Millisecond,
		MaxBatchSize:    30,
		MaxQueueSize:    1000,
		FlushOnShutdown: true,
	}
}

// WebSocketBatcher batches WebSocket messages to reduce network overhead
type WebSocketBatcher struct {
	config       BatcherConfig
	batches      map[string][]Message // event -> messages
	timers       map[string]*time.Timer
	mu           sync.RWMutex
	emitter      MessageEmitter
	running      bool
	stopChan     chan struct{}
	wg           sync.WaitGroup
	droppedCount int64
	sentCount    int64
}

// MessageEmitter is the interface for sending batches
type MessageEmitter interface {
	Emit(event string, data interface{}) error
	EmitToRoom(event string, room string, data interface{}) error
}

// NewWebSocketBatcher creates a new WebSocket batcher
func NewWebSocketBatcher(emitter MessageEmitter, config BatcherConfig) *WebSocketBatcher {
	if config.BatchInterval == 0 {
		config = DefaultBatcherConfig()
	}

	return &WebSocketBatcher{
		config:   config,
		batches:  make(map[string][]Message),
		timers:   make(map[string]*time.Timer),
		emitter:  emitter,
		running:  true,
		stopChan: make(chan struct{}),
	}
}

// Emit queues a message for batched emission
func (wb *WebSocketBatcher) Emit(event string, data map[string]interface{}, room string) error {
	if !wb.running {
		return fmt.Errorf("batcher is not running")
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
	if len(wb.batches[event]) >= wb.config.MaxBatchSize {
		go wb.flushBatch(event, room)
		return nil
	}

	// Set/reset timer for this event (mutex already held)
	if timer, exists := wb.timers[event]; exists {
		timer.Stop()
	}

	wb.timers[event] = time.AfterFunc(wb.config.BatchInterval, func() {
		wb.flushBatch(event, room)
	})

	return nil
}

// flushBatch sends all pending messages for an event
func (wb *WebSocketBatcher) flushBatch(event string, room string) {
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

	// Send the batch
	var err error
	if room != "" {
		err = wb.emitter.EmitToRoom(batch.Event, room, batch)
	} else {
		err = wb.emitter.Emit(batch.Event, batch)
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

	// Stop all timers
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

	return map[string]interface{}{
		"running":           wb.running,
		"total_queued":      totalQueued,
		"dropped_count":     wb.droppedCount,
		"sent_count":        wb.sentCount,
		"batch_count":       len(wb.batches),
		"batch_interval_ms": wb.config.BatchInterval.Milliseconds(),
		"max_batch_size":    wb.config.MaxBatchSize,
		"max_queue_size":    wb.config.MaxQueueSize,
	}
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
