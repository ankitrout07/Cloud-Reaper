package rag

import (
	"math"
	"regexp"
	"sort"
	"strings"
	"sync"
)

// Document represents a chunk of indexed document with vector embedding
type Document struct {
	ID           string                 `json:"id"`
	FileName     string                 `json:"file_name"`
	Text         string                 `json:"text"`
	Sentence     string                 `json:"sentence"`
	LeftContext  string                 `json:"left_context"`
	RightContext string                 `json:"right_context"`
	Vector       []float64              `json:"vector"`
	Metadata     map[string]interface{} `json:"metadata"`
}

// SearchQuery represents a search request
type SearchQuery struct {
	Query          string    `json:"query"`
	QueryVector    []float64 `json:"query_vector,omitempty"`
	TopK           int       `json:"top_k"`
	FileFilter     string    `json:"file_filter,omitempty"`
	FileTypeFilter string    `json:"file_type_filter,omitempty"`
	LambdaParam    float64   `json:"lambda_param"` // For MMR diversity
	RRFConstant    int       `json:"rrf_constant"`
	EnableBM25     bool      `json:"enable_bm25"`
	EnableDense    bool      `json:"enable_dense"`
	EnableMMR      bool      `json:"enable_mmr"`
}

// SearchResult represents a search result
type SearchResult struct {
	Document      Document `json:"document"`
	Score         float64  `json:"score"`
	Confidence    float64  `json:"confidence"`
	RankingMethod string   `json:"ranking_method"`
}

// BM25Index represents the BM25 sparse search index
type BM25Index struct {
	docFreqs     map[string]int
	docLengths   []int
	docTermFreqs []map[string]int
	avgDocLength float64
	N            int
	k1           float64
	b            float64
	mu           sync.RWMutex
}

// VectorIndex represents the dense vector search index
type VectorIndex struct {
	documents []Document
	mu        sync.RWMutex
}

// RAGEngine represents the hybrid RAG search engine
type RAGEngine struct {
	bm25Index      *BM25Index
	vectorIndex    *VectorIndex
	documents      []Document
	domainSynonyms map[string][]string
	mu             sync.RWMutex
}

// NewRAGEngine creates a new RAG search engine
func NewRAGEngine() *RAGEngine {
	return &RAGEngine{
		bm25Index: &BM25Index{
			docFreqs:     make(map[string]int),
			docLengths:   make([]int, 0),
			docTermFreqs: make([]map[string]int, 0),
			k1:           1.5,
			b:            0.75,
		},
		vectorIndex: &VectorIndex{
			documents: make([]Document, 0),
		},
		documents: make([]Document, 0),
		domainSynonyms: map[string][]string{
			"cost":     {"price", "expense", "spending", "budget", "billing", "financial"},
			"optimize": {"improve", "reduce", "minimize", "cut", "save", "efficiency"},
			"vm":       {"virtual machine", "instance", "compute", "server", "workload"},
			"azure":    {"microsoft", "cloud", "subscription", "tenant"},
			"storage":  {"disk", "blob", "file", "data", "persistence"},
			"network":  {"vnet", "subnet", "connectivity", "routing", "firewall"},
			"security": {"access", "permission", "auth", "authentication", "identity"},
			"monitor":  {"track", "observe", "metric", "telemetry", "log"},
			"scale":    {"autoscale", "elastic", "grow", "shrink", "capacity"},
		},
	}
}

// IndexDocuments indexes a batch of documents with their embeddings
func (re *RAGEngine) IndexDocuments(docs []Document) error {
	re.mu.Lock()
	defer re.mu.Unlock()

	re.documents = append(re.documents, docs...)
	re.vectorIndex.documents = append(re.vectorIndex.documents, docs...)

	// Build BM25 index
	re.buildBM25Index()

	return nil
}

// buildBM25Index builds the BM25 sparse search index
func (re *RAGEngine) buildBM25Index() {
	re.mu.Lock()
	defer re.mu.Unlock()

	bm25 := re.bm25Index
	bm25.mu.Lock()
	defer bm25.mu.Unlock()

	bm25.docFreqs = make(map[string]int)
	bm25.docLengths = make([]int, 0)
	bm25.docTermFreqs = make([]map[string]int, 0)

	totalLength := 0
	bm25.N = len(re.documents)

	for _, doc := range re.documents {
		text := doc.Text
		if text == "" {
			text = doc.Sentence
		}

		tokens := tokenize(text)
		docLen := len(tokens)
		totalLength += docLen

		bm25.docLengths = append(bm25.docLengths, docLen)

		termFreqs := make(map[string]int)
		for _, token := range tokens {
			termFreqs[token]++
		}
		bm25.docTermFreqs = append(bm25.docTermFreqs, termFreqs)

		for term := range termFreqs {
			bm25.docFreqs[term]++
		}
	}

	if bm25.N > 0 {
		bm25.avgDocLength = float64(totalLength) / float64(bm25.N)
	}
}

// tokenize splits text into lowercase word tokens
func tokenize(text string) []string {
	re := regexp.MustCompile(`\w+`)
	matches := re.FindAllString(strings.ToLower(text), -1)
	return matches
}

// DenseSearch performs cosine similarity search using vector embeddings
func (re *RAGEngine) DenseSearch(queryVector []float64, topK int) []SearchResult {
	re.mu.RLock()
	defer re.mu.RUnlock()

	re.vectorIndex.mu.RLock()
	defer re.vectorIndex.mu.RUnlock()

	if len(queryVector) == 0 || len(re.vectorIndex.documents) == 0 {
		return []SearchResult{}
	}

	queryNorm := normalize(queryVector)
	scores := make([]float64, len(re.vectorIndex.documents))

	// Calculate cosine similarity for each document
	for i, doc := range re.vectorIndex.documents {
		if len(doc.Vector) != len(queryVector) {
			scores[i] = 0.0
			continue
		}

		docNorm := normalize(doc.Vector)
		dotProduct := dotProduct(queryVector, doc.Vector)

		if queryNorm > 0 && docNorm > 0 {
			scores[i] = dotProduct / (queryNorm * docNorm)
		} else {
			scores[i] = 0.0
		}
	}

	// Sort by score descending
	indices := make([]int, len(scores))
	for i := range indices {
		indices[i] = i
	}
	sort.Slice(indices, func(i, j int) bool {
		return scores[indices[i]] > scores[indices[j]]
	})

	// Return top K results with document indices for RRF
	results := make([]SearchResult, 0, topK)
	for i := 0; i < topK && i < len(indices); i++ {
		idx := indices[i]
		// Store the original document index in metadata for RRF mapping
		doc := re.vectorIndex.documents[idx]
		if doc.Metadata == nil {
			doc.Metadata = make(map[string]interface{})
		}
		doc.Metadata["original_index"] = idx

		results = append(results, SearchResult{
			Document:      doc,
			Score:         scores[idx],
			Confidence:    scores[idx] * 100,
			RankingMethod: "dense_vector",
		})
	}

	return results
}

// SparseSearch performs BM25 keyword search
func (re *RAGEngine) SparseSearch(query string, topK int) []SearchResult {
	re.mu.RLock()
	defer re.mu.RUnlock()

	re.bm25Index.mu.RLock()
	defer re.bm25Index.mu.RUnlock()

	if re.bm25Index.N == 0 {
		return []SearchResult{}
	}

	queryTokens := tokenize(query)
	scores := make([]float64, re.bm25Index.N)

	// Calculate BM25 score for each document
	for docIdx := 0; docIdx < re.bm25Index.N; docIdx++ {
		score := 0.0
		docLen := re.bm25Index.docLengths[docIdx]
		termFreqs := re.bm25Index.docTermFreqs[docIdx]

		for _, term := range queryTokens {
			df, exists := re.bm25Index.docFreqs[term]
			if !exists {
				continue
			}

			// IDF calculation with smoothing
			idf := math.Log(1 + (float64(re.bm25Index.N-df)+0.5)/(float64(df)+0.5))

			tf := termFreqs[term]
			numerator := float64(tf) * (re.bm25Index.k1 + 1)
			denominator := float64(tf) + re.bm25Index.k1*(1-re.bm25Index.b+re.bm25Index.b*(float64(docLen)/re.bm25Index.avgDocLength))

			score += idf * (numerator / denominator)
		}

		scores[docIdx] = score
	}

	// Sort by score descending
	indices := make([]int, len(scores))
	for i := range indices {
		indices[i] = i
	}
	sort.Slice(indices, func(i, j int) bool {
		return scores[indices[i]] > scores[indices[j]]
	})

	// Return top K results with document indices for RRF
	results := make([]SearchResult, 0, topK)
	for i := 0; i < topK && i < len(indices); i++ {
		idx := indices[i]
		// Store the original document index in metadata for RRF mapping
		doc := re.documents[idx]
		if doc.Metadata == nil {
			doc.Metadata = make(map[string]interface{})
		}
		doc.Metadata["original_index"] = idx

		results = append(results, SearchResult{
			Document:      doc,
			Score:         scores[idx],
			Confidence:    scores[idx] * 10, // Scale BM25 scores to 0-100 range
			RankingMethod: "bm25_sparse",
		})
	}

	return results
}

// HybridSearch combines dense and sparse search using Reciprocal Rank Fusion (RRF)
func (re *RAGEngine) HybridSearch(query SearchQuery) []SearchResult {
	re.mu.RLock()
	defer re.mu.RUnlock()

	// Apply metadata filters
	filteredIndices := re.applyFilters(query)

	if len(filteredIndices) == 0 {
		return []SearchResult{}
	}

	// Query expansion
	expandedQueries := re.expandQuery(query.Query)

	// Aggregate RRF scores across all query variants
	rrfScores := make(map[int]float64)
	rrfConstant := query.RRFConstant
	if rrfConstant == 0 {
		rrfConstant = 60
	}

	for _, expandedQuery := range expandedQueries {
		// Dense search
		var denseRanks map[int]int
		if query.EnableDense && len(query.QueryVector) > 0 {
			denseResults := re.DenseSearch(query.QueryVector, len(re.documents))
			denseRanks = make(map[int]int)
			// Use the original_index stored in metadata during search
			for rank, result := range denseResults {
				if originalIndex, ok := result.Document.Metadata["original_index"].(int); ok {
					denseRanks[originalIndex] = rank + 1
				}
			}
		}

		// Sparse search
		var sparseRanks map[int]int
		if query.EnableBM25 {
			sparseResults := re.SparseSearch(expandedQuery, len(re.documents))
			sparseRanks = make(map[int]int)
			// Use the original_index stored in metadata during search
			for rank, result := range sparseResults {
				if originalIndex, ok := result.Document.Metadata["original_index"].(int); ok {
					sparseRanks[originalIndex] = rank + 1
				}
			}
		}

		// Calculate RRF scores for filtered indices
		for idx := range filteredIndices {
			rDense := len(re.documents) + 1
			rSparse := len(re.documents) + 1

			if denseRanks != nil {
				if rank, exists := denseRanks[idx]; exists {
					rDense = rank
				}
			}

			if sparseRanks != nil {
				if rank, exists := sparseRanks[idx]; exists {
					rSparse = rank
				}
			}

			rrfScore := 1.0/float64(rrfConstant+rDense) + 1.0/float64(rrfConstant+rSparse)

			if existingScore, exists := rrfScores[idx]; exists {
				rrfScores[idx] = math.Max(existingScore, rrfScore)
			} else {
				rrfScores[idx] = rrfScore
			}
		}
	}

	// Convert to sorted results
	type rankedResult struct {
		Index int
		Score float64
	}
	rankedResults := make([]rankedResult, 0, len(rrfScores))
	for idx, score := range rrfScores {
		rankedResults = append(rankedResults, rankedResult{Index: idx, Score: score})
	}
	sort.Slice(rankedResults, func(i, j int) bool {
		return rankedResults[i].Score > rankedResults[j].Score
	})

	// Convert to SearchResult format
	results := make([]SearchResult, 0, query.TopK)
	for i := 0; i < query.TopK && i < len(rankedResults); i++ {
		idx := rankedResults[i].Index
		results = append(results, SearchResult{
			Document:      re.documents[idx],
			Score:         rankedResults[i].Score,
			Confidence:    rankedResults[i].Score * 100,
			RankingMethod: "hybrid_rrf",
		})
	}

	// Apply MMR diversification if enabled
	if query.EnableMMR {
		results = re.applyMMR(results, query.LambdaParam, query.TopK)
	}

	return results
}

// applyFilters applies metadata filters to document indices
func (re *RAGEngine) applyFilters(query SearchQuery) map[int]bool {
	filteredIndices := make(map[int]bool)

	for idx := range re.documents {
		filteredIndices[idx] = true
	}

	if query.FileFilter != "" {
		for idx := range re.documents {
			if !strings.Contains(strings.ToLower(re.documents[idx].FileName), strings.ToLower(query.FileFilter)) {
				delete(filteredIndices, idx)
			}
		}
	}

	if query.FileTypeFilter != "" {
		for idx := range re.documents {
			fileType, ok := re.documents[idx].Metadata["file_type"].(string)
			if !ok || fileType != query.FileTypeFilter {
				delete(filteredIndices, idx)
			}
		}
	}

	return filteredIndices
}

// expandQuery expands the query with domain-specific synonyms
func (re *RAGEngine) expandQuery(query string) []string {
	queries := []string{query}
	queryLower := strings.ToLower(query)

	// Domain-specific synonym expansion
	for term, synonyms := range re.domainSynonyms {
		if strings.Contains(queryLower, term) {
			for _, synonym := range synonyms {
				expandedQuery := strings.ReplaceAll(queryLower, term, synonym)
				if expandedQuery != queryLower {
					queries = append(queries, expandedQuery)
				}
			}
		}
	}

	return queries
}

// applyMMR applies Maximal Marginal Relevance for result diversification
func (re *RAGEngine) applyMMR(results []SearchResult, lambdaParam float64, topK int) []SearchResult {
	if len(results) == 0 {
		return results
	}

	selected := make([]SearchResult, 0)
	remaining := make([]SearchResult, len(results))
	copy(remaining, results)

	// Select highest scoring result first
	if len(remaining) > 0 {
		selected = append(selected, remaining[0])
		remaining = remaining[1:]
	}

	for len(selected) < topK && len(remaining) > 0 {
		bestIdx := 0
		bestMMR := math.Inf(-1)

		for i, result := range remaining {
			relevance := result.Score

			// Calculate diversity component (minimum similarity to already selected)
			maxSimilarity := 0.0
			for _, selectedResult := range selected {
				similarity := re.cosineSimilarity(result.Document.Vector, selectedResult.Document.Vector)
				if similarity > maxSimilarity {
					maxSimilarity = similarity
				}
			}

			// MMR score: lambda * relevance - (1-lambda) * max_similarity
			mmrScore := lambdaParam*relevance - (1-lambdaParam)*maxSimilarity

			if mmrScore > bestMMR {
				bestMMR = mmrScore
				bestIdx = i
			}
		}

		selected = append(selected, remaining[bestIdx])
		remaining = append(remaining[:bestIdx], remaining[bestIdx+1:]...)
	}

	return selected
}

// cosineSimilarity calculates cosine similarity between two vectors
func (re *RAGEngine) cosineSimilarity(vec1, vec2 []float64) float64 {
	if len(vec1) != len(vec2) || len(vec1) == 0 {
		return 0.0
	}

	norm1 := normalize(vec1)
	norm2 := normalize(vec2)
	dotProd := dotProduct(vec1, vec2)

	if norm1 > 0 && norm2 > 0 {
		return dotProd / (norm1 * norm2)
	}
	return 0.0
}

// normalize calculates the L2 norm of a vector
func normalize(vec []float64) float64 {
	sum := 0.0
	for _, v := range vec {
		sum += v * v
	}
	return math.Sqrt(sum)
}

// dotProduct calculates the dot product of two vectors
func dotProduct(vec1, vec2 []float64) float64 {
	sum := 0.0
	for i := range vec1 {
		sum += vec1[i] * vec2[i]
	}
	return sum
}

// ClearIndex clears all indexed documents
func (re *RAGEngine) ClearIndex() {
	re.mu.Lock()
	defer re.mu.Unlock()

	re.documents = make([]Document, 0)
	re.vectorIndex.documents = make([]Document, 0)
	re.buildBM25Index()
}

// GetDocumentCount returns the number of indexed documents
func (re *RAGEngine) GetDocumentCount() int {
	re.mu.RLock()
	defer re.mu.RUnlock()
	return len(re.documents)
}

// GetStatistics returns engine statistics
func (re *RAGEngine) GetStatistics() map[string]interface{} {
	re.mu.RLock()
	defer re.mu.RUnlock()

	return map[string]interface{}{
		"total_documents": len(re.documents),
		"bm25_indexed":    re.bm25Index.N,
		"vector_indexed":  len(re.vectorIndex.documents),
		"avg_doc_length":  re.bm25Index.avgDocLength,
		"unique_terms":    len(re.bm25Index.docFreqs),
		"domain_synonyms": len(re.domainSynonyms),
	}
}
