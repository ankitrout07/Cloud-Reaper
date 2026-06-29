package rag

import (
	"encoding/json"
	"log"
	"net/http"
	"strconv"
	"sync"
)

// Global RAG engine instance
var (
	globalRAGEngine *RAGEngine
	ragInit        sync.Once
)

// GetRAGEngine returns the singleton RAG engine instance
func GetRAGEngine() *RAGEngine {
	ragInit.Do(func() {
		globalRAGEngine = NewRAGEngine()
		log.Println("[RAG Engine] Initialized RAG search engine")
	})
	return globalRAGEngine
}

// HTTPResponse is a standard response wrapper
type HTTPResponse struct {
	Success bool        `json:"success"`
	Data    interface{} `json:"data,omitempty"`
	Error   string      `json:"error,omitempty"`
}

// IndexRequest represents a request to index documents
type IndexRequest struct {
	Documents []Document `json:"documents"`
}

// SearchRequest represents a search request
type SearchRequest struct {
	Query          string   `json:"query"`
	QueryVector    []float64 `json:"query_vector,omitempty"`
	TopK           int      `json:"top_k"`
	FileFilter     string   `json:"file_filter,omitempty"`
	FileTypeFilter string   `json:"file_type_filter,omitempty"`
	LambdaParam    float64  `json:"lambda_param"`
	RRFConstant    int      `json:"rrf_constant"`
	EnableBM25     bool     `json:"enable_bm25"`
	EnableDense    bool     `json:"enable_dense"`
	EnableMMR      bool     `json:"enable_mmr"`
}

// RegisterRAGHandlers registers HTTP handlers for RAG search
func RegisterRAGHandlers(mux *http.ServeMux) {
	rag := GetRAGEngine()

	// Health check endpoint
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		sendJSONResponse(w, map[string]string{
			"status":  "healthy",
			"service": "rag_search",
		})
	})

	// Index documents
	mux.HandleFunc("/api/rag/index", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req IndexRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if err := rag.IndexDocuments(req.Documents); err != nil {
			sendJSONError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		sendJSONResponse(w, map[string]interface{}{
			"indexed_count": len(req.Documents),
			"total_docs":    rag.GetDocumentCount(),
		})
	})

	// Search documents
	mux.HandleFunc("/api/rag/search", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req SearchRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		// Set defaults
		if req.TopK == 0 {
			req.TopK = 10
		}
		if req.LambdaParam == 0 {
			req.LambdaParam = 0.6
		}
		if req.RRFConstant == 0 {
			req.RRFConstant = 60
		}
		if !req.EnableBM25 && !req.EnableDense {
			// Enable both by default
			req.EnableBM25 = true
			req.EnableDense = true
		}

		query := SearchQuery{
			Query:          req.Query,
			QueryVector:    req.QueryVector,
			TopK:           req.TopK,
			FileFilter:     req.FileFilter,
			FileTypeFilter: req.FileTypeFilter,
			LambdaParam:     req.LambdaParam,
			RRFConstant:     req.RRFConstant,
			EnableBM25:      req.EnableBM25,
			EnableDense:     req.EnableDense,
			EnableMMR:       req.EnableMMR,
		}

		results := rag.HybridSearch(query)

		sendJSONResponse(w, map[string]interface{}{
			"results":      results,
			"total_found":  len(results),
			"query_params": query,
		})
	})

	// Dense search only
	mux.HandleFunc("/api/rag/dense", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req struct {
			QueryVector []float64 `json:"query_vector"`
			TopK        int      `json:"top_k"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if req.TopK == 0 {
			req.TopK = 10
		}

		results := rag.DenseSearch(req.QueryVector, req.TopK)

		sendJSONResponse(w, map[string]interface{}{
			"results":     results,
			"total_found": len(results),
		})
	})

	// Sparse search only
	mux.HandleFunc("/api/rag/sparse", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req struct {
			Query string `json:"query"`
			TopK  int    `json:"top_k"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if req.TopK == 0 {
			req.TopK = 10
		}

		results := rag.SparseSearch(req.Query, req.TopK)

		sendJSONResponse(w, map[string]interface{}{
			"results":     results,
			"total_found": len(results),
		})
	})

	// Clear index
	mux.HandleFunc("/api/rag/clear", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		rag.ClearIndex()

		sendJSONResponse(w, map[string]string{
			"status": "cleared",
		})
	})

	// Get statistics
	mux.HandleFunc("/api/rag/stats", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		stats := rag.GetStatistics()
		sendJSONResponse(w, stats)
	})

	// Query expansion
	mux.HandleFunc("/api/rag/expand", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req struct {
			Query string `json:"query"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			sendJSONError(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		expanded := rag.expandQuery(req.Query)

		sendJSONResponse(w, map[string]interface{}{
			"original":  req.Query,
			"expanded":  expanded,
			"count":     len(expanded),
		})
	})
}

// Helper functions for HTTP responses
func sendJSONResponse(w http.ResponseWriter, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(HTTPResponse{
		Success: true,
		Data:    data,
	})
}

func sendJSONError(w http.ResponseWriter, message string, statusCode int) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	json.NewEncoder(w).Encode(HTTPResponse{
		Success: false,
		Error:   message,
	})
}

// StartRAGServer starts the RAG search HTTP server
func StartRAGServer(port int) error {
	mux := http.NewServeMux()
	RegisterRAGHandlers(mux)

	addr := ":" + strconv.Itoa(port)
	log.Printf("Starting RAG search server on %s", addr)
	return http.ListenAndServe(addr, mux)
}