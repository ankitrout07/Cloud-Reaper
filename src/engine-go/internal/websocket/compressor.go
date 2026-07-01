package websocket

import (
	"bytes"
	"compress/gzip"
	"encoding/json"
	"fmt"
	"io"
	"sync"
)

// CompressionType represents the compression algorithm
type CompressionType string

const (
	CompressionNone CompressionType = "none"
	CompressionGzip CompressionType = "gzip"
	CompressionSnappy CompressionType = "snappy"
)

// MessageCompressor handles WebSocket message compression
type MessageCompressor struct {
	compressionType CompressionType
	compressionLevel int
	bufferPool      *sync.Pool
	stats           CompressionStats
	mu              sync.RWMutex
}

// CompressionStats tracks compression statistics
type CompressionStats struct {
	TotalMessages     int64
	CompressedSize    int64
	OriginalSize     int64
	CompressionRatio float64
	TotalSavings     int64
}

// CompressorConfig holds configuration for the compressor
type CompressorConfig struct {
	Type           CompressionType
	CompressionLevel int // For gzip: 1-9, default 6
	BufferSize     int
}

// DefaultCompressorConfig returns sensible defaults
func DefaultCompressorConfig() CompressorConfig {
	return CompressorConfig{
		Type:           CompressionGzip,
		CompressionLevel: 6,
		BufferSize:     4096,
	}
}

// NewMessageCompressor creates a new message compressor
func NewMessageCompressor(config CompressorConfig) *MessageCompressor {
	if config.CompressionLevel == 0 {
		config.CompressionLevel = 6
	}

	return &MessageCompressor{
		compressionType: config.Type,
		compressionLevel: config.CompressionLevel,
		bufferPool: &sync.Pool{
			New: func() interface{} {
				return bytes.NewBuffer(make([]byte, 0, config.BufferSize))
			},
		},
	}
}

// Compress compresses a message using the configured algorithm
func (mc *MessageCompressor) Compress(data []byte) ([]byte, error) {
	if mc.compressionType == CompressionNone {
		return data, nil
	}

	mc.mu.Lock()
	defer mc.mu.Unlock()

	originalSize := len(data)
	var compressed []byte
	var err error

	switch mc.compressionType {
	case CompressionGzip:
		compressed, err = mc.compressGzip(data)
	case CompressionSnappy:
		compressed, err = mc.compressSnappy(data)
	default:
		return data, nil
	}

	if err != nil {
		return nil, fmt.Errorf("compression failed: %w", err)
	}

	// Update statistics
	mc.stats.TotalMessages++
	mc.stats.OriginalSize += int64(originalSize)
	mc.stats.CompressedSize += int64(len(compressed))
	mc.stats.TotalSavings += int64(originalSize - len(compressed))

	if mc.stats.OriginalSize > 0 {
		mc.stats.CompressionRatio = float64(mc.stats.CompressedSize) / float64(mc.stats.OriginalSize)
	}

	// Return original if compression didn't help
	if len(compressed) >= originalSize {
		return data, nil
	}

	return compressed, nil
}

// compressGzip compresses data using gzip
func (mc *MessageCompressor) compressGzip(data []byte) ([]byte, error) {
	buffer := mc.bufferPool.Get().(*bytes.Buffer)
	buffer.Reset()
	defer mc.bufferPool.Put(buffer)

	writer, err := gzip.NewWriterLevel(buffer, mc.compressionLevel)
	if err != nil {
		return nil, err
	}

	if _, err := writer.Write(data); err != nil {
		writer.Close()
		return nil, err
	}

	if err := writer.Close(); err != nil {
		return nil, err
	}

	result := make([]byte, buffer.Len())
	copy(result, buffer.Bytes())
	return result, nil
}

// compressSnappy compresses data using snappy (simplified implementation)
func (mc *MessageCompressor) compressSnappy(data []byte) ([]byte, error) {
	// Simplified snappy-like compression
	// For production, use the actual snappy-go library
	
	if len(data) < 100 {
		return data, nil
	}

	// Simple run-length encoding for demonstration
	buffer := mc.bufferPool.Get().(*bytes.Buffer)
	buffer.Reset()
	defer mc.bufferPool.Put(buffer)

	count := 1
	for i := 1; i < len(data); i++ {
		if data[i] == data[i-1] && count < 255 {
			count++
		} else {
			buffer.WriteByte(byte(count))
			buffer.WriteByte(data[i-1])
			count = 1
		}
	}
	buffer.WriteByte(byte(count))
	buffer.WriteByte(data[len(data)-1])

	result := make([]byte, buffer.Len())
	copy(result, buffer.Bytes())
	return result, nil
}

// Decompress decompresses a message
func (mc *MessageCompressor) Decompress(data []byte) ([]byte, error) {
	if mc.compressionType == CompressionNone {
		return data, nil
	}

	switch mc.compressionType {
	case CompressionGzip:
		return mc.decompressGzip(data)
	case CompressionSnappy:
		return mc.decompressSnappy(data)
	default:
		return data, nil
	}
}

// decompressGzip decompresses gzip data
func (mc *MessageCompressor) decompressGzip(data []byte) ([]byte, error) {
	reader, err := gzip.NewReader(bytes.NewReader(data))
	if err != nil {
		return nil, err
	}
	defer reader.Close()

	result, err := io.ReadAll(reader)
	if err != nil {
		return nil, err
	}

	return result, nil
}

// decompressSnappy decompresses snappy data
func (mc *MessageCompressor) decompressSnappy(data []byte) ([]byte, error) {
	// Simplified decompression for the run-length encoding
	buffer := mc.bufferPool.Get().(*bytes.Buffer)
	buffer.Reset()
	defer mc.bufferPool.Put(buffer)

	for i := 0; i < len(data); i += 2 {
		count := int(data[i])
		value := data[i+1]
		for j := 0; j < count; j++ {
			buffer.WriteByte(value)
		}
	}

	result := make([]byte, buffer.Len())
	copy(result, buffer.Bytes())
	return result, nil
}

// CompressBatch compresses a batch of messages
func (mc *MessageCompressor) CompressBatch(batch Batch) (*CompressedBatch, error) {
	// Serialize batch to JSON
	jsonData, err := json.Marshal(batch)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal batch: %w", err)
	}

	// Compress the JSON data
	compressed, err := mc.Compress(jsonData)
	if err != nil {
		return nil, err
	}

	return &CompressedBatch{
		Event:          batch.Event,
		CompressedData: compressed,
		OriginalSize:   len(jsonData),
		CompressedSize: len(compressed),
		Count:          batch.Count,
		CompressionType: mc.compressionType,
	}, nil
}

// DecompressBatch decompresses a compressed batch
func (mc *MessageCompressor) DecompressBatch(compressedBatch *CompressedBatch) (*Batch, error) {
	// Decompress the data
	decompressed, err := mc.Decompress(compressedBatch.CompressedData)
	if err != nil {
		return nil, fmt.Errorf("decompression failed: %w", err)
	}

	// Deserialize the batch
	var batch Batch
	if err := json.Unmarshal(decompressed, &batch); err != nil {
		return nil, fmt.Errorf("failed to unmarshal batch: %w", err)
	}

	return &batch, nil
}

// CompressedBatch represents a compressed batch
type CompressedBatch struct {
	Event           string        `json:"event"`
	CompressedData  []byte        `json:"compressed_data"`
	OriginalSize    int           `json:"original_size"`
	CompressedSize  int           `json:"compressed_size"`
	Count           int           `json:"count"`
	CompressionType CompressionType `json:"compression_type"`
}

// GetStats returns compression statistics
func (mc *MessageCompressor) GetStats() CompressionStats {
	mc.mu.RLock()
	defer mc.mu.RUnlock()
	return mc.stats
}

// ResetStats resets compression statistics
func (mc *MessageCompressor) ResetStats() {
	mc.mu.Lock()
	defer mc.mu.Unlock()
	mc.stats = CompressionStats{}
}

// SetCompressionType changes the compression type
func (mc *MessageCompressor) SetCompressionType(compressionType CompressionType) {
	mc.mu.Lock()
	defer mc.mu.Unlock()
	mc.compressionType = compressionType
}

// GetCompressionType returns the current compression type
func (mc *MessageCompressor) GetCompressionType() CompressionType {
	mc.mu.RLock()
	defer mc.mu.RUnlock()
	return mc.compressionType
}

// AdaptiveCompressor automatically selects the best compression based on message size
type AdaptiveCompressor struct {
	smallCompressor *MessageCompressor
	largeCompressor *MessageCompressor
	threshold      int
}

// NewAdaptiveCompressor creates a new adaptive compressor
func NewAdaptiveCompressor(threshold int) *AdaptiveCompressor {
	if threshold == 0 {
		threshold = 1024 // 1KB threshold
	}

	return &AdaptiveCompressor{
		smallCompressor: NewMessageCompressor(CompressorConfig{
			Type:           CompressionNone, // No compression for small messages
			CompressionLevel: 6,
		}),
		largeCompressor: NewMessageCompressor(CompressorConfig{
			Type:           CompressionGzip,
			CompressionLevel: 6,
		}),
		threshold: threshold,
	}
}

// Compress adaptively compresses based on message size
func (ac *AdaptiveCompressor) Compress(data []byte) ([]byte, error) {
	if len(data) < ac.threshold {
		return ac.smallCompressor.Compress(data)
	}
	return ac.largeCompressor.Compress(data)
}

// Decompress adaptively decompresses based on message size
func (ac *AdaptiveCompressor) Decompress(data []byte) ([]byte, error) {
	if len(data) < ac.threshold {
		return ac.smallCompressor.Decompress(data)
	}
	return ac.largeCompressor.Decompress(data)
}

// GetCombinedStats returns combined statistics from both compressors
func (ac *AdaptiveCompressor) GetCombinedStats() map[string]CompressionStats {
	return map[string]CompressionStats{
		"small": ac.smallCompressor.GetStats(),
		"large": ac.largeCompressor.GetStats(),
	}
}
