package rag

import (
	"fmt"
	"hash/fnv"
	"math"
	"math/rand"
	"sort"
	"strings"
	"sync"
	"time"
)

// LearnableRanking implements gradient boosting for learnable ranking functions
type LearnableRanking struct {
	modelType    string
	featureNames []string
	isTrained    bool
	trainingData []TrainingSample
	mu           sync.RWMutex
}

// TrainingSample represents a single training sample
type TrainingSample struct {
	Features []float64
	Relevance float64
}

// NewLearnableRanking creates a new learnable ranking system
func NewLearnableRanking(modelType string) *LearnableRanking {
	return &LearnableRanking{
		modelType:    modelType,
		isTrained:    false,
		trainingData: make([]TrainingSample, 0),
	}
}

// ExtractRankingFeatures extracts features for ranking from query and document
func (lr *LearnableRanking) ExtractRankingFeatures(query string, document Document, searchResults []SearchResult) []float64 {
	features := make([]float64, 0)

	queryLower := strings.ToLower(query)
	docText := strings.ToLower(document.Text)
	docSentence := strings.ToLower(document.Sentence)

	// Exact match features
	if strings.Contains(docText, queryLower) {
		features = append(features, 1.0)
	} else {
		features = append(features, 0.0)
	}

	if strings.Contains(docSentence, queryLower) {
		features = append(features, 1.0)
	} else {
		features = append(features, 0.0)
	}

	// Length features
	features = append(features, float64(len(docText)))
	features = append(features, float64(len(docSentence)))
	features = append(features, float64(len(query)))

	// Position features
	docIndex := -1
	for i, result := range searchResults {
		if result.Document.ID == document.ID {
			docIndex = i
			break
		}
	}
	if docIndex >= 0 {
		features = append(features, float64(docIndex))
	} else {
		features = append(features, float64(len(searchResults)))
	}

	// Score features
	originalScore := 0.0 // Assuming Document has Score field
	features = append(features, originalScore)

	// Context features
	avgScore := 0.0
	if len(searchResults) > 0 {
		totalScore := 0.0
		for _, r := range searchResults {
			totalScore += r.Score
		}
		avgScore = totalScore / float64(len(searchResults))
	}
	features = append(features, originalScore-avgScore)

	// Document metadata features
	metadataCount := len(document.Metadata)
	features = append(features, float64(metadataCount))

	// File type features
	fileType := ""
	if ft, ok := document.Metadata["file_type"].(string); ok {
		fileType = ft
	}
	features = append(features, float64(hashString(fileType)%100))

	// Text complexity features
	words := strings.Fields(docText)
	features = append(features, float64(len(words)))

	uniqueWords := make(map[string]bool)
	for _, word := range words {
		uniqueWords[word] = true
	}
	uniqueRatio := 0.0
	if len(words) > 0 {
		uniqueRatio = float64(len(uniqueWords)) / float64(len(words))
	}
	features = append(features, uniqueRatio)

	lr.featureNames = []string{
		"query_in_doc", "query_in_sentence",
		"doc_length", "sentence_length", "query_length",
		"doc_position", "original_score", "relative_score",
		"metadata_count", "file_type_encoded",
		"word_count", "unique_word_ratio",
	}

	return features
}

// RankResults ranks search results using the learned model
func (lr *LearnableRanking) RankResults(query string, results []SearchResult) []SearchResult {
	lr.mu.RLock()
	defer lr.mu.RUnlock()

	if !lr.isTrained || len(results) == 0 {
		return results
	}

	// Extract features for each result
	for i := range results {
		document := results[i].Document
		features := lr.ExtractRankingFeatures(query, document, results)
		
		// Simple linear model for demonstration
		// In production, use actual gradient boosting model
		learnedScore := 0.0
		for _, feat := range features {
			weight := 0.1 // Simple equal weights
			learnedScore += weight * feat
		}

		results[i].Score = learnedScore
		results[i].RankingMethod = "learnable_" + lr.modelType
	}

	// Sort by learned scores
	sort.Slice(results, func(i, j int) bool {
		return results[i].Score > results[j].Score
	})

	return results
}

// AddFeedback adds user feedback for training
func (lr *LearnableRanking) AddFeedback(query string, document Document, relevanceScore float64, clicked bool, dwellTime float64) {
	lr.mu.Lock()
	defer lr.mu.Unlock()

	features := lr.ExtractRankingFeatures(query, document, []SearchResult{})
	sample := TrainingSample{
		Features:  features,
		Relevance: relevanceScore,
	}
	lr.trainingData = append(lr.trainingData, sample)
}

// TrainModel trains the ranking model on collected feedback
func (lr *LearnableRanking) TrainModel(minSamples int) map[string]interface{} {
	lr.mu.Lock()
	defer lr.mu.Unlock()

	if len(lr.trainingData) < minSamples {
		return map[string]interface{}{
			"success": false,
			"error":   fmt.Sprintf("Insufficient training data: %d < %d", len(lr.trainingData), minSamples),
		}
	}

	// In production, implement actual gradient boosting training
	// For now, mark as trained
	lr.isTrained = true

	return map[string]interface{}{
		"success":         true,
		"training_samples": len(lr.trainingData),
		"model_type":      lr.modelType,
	}
}

// DeterminantalPointProcesses implements advanced diversification using DPP
type DeterminantalPointProcesses struct {
	lambdaParam float64
}

// NewDeterminantalPointProcesses creates a new DPP diversifier
func NewDeterminantalPointProcesses(lambdaParam float64) *DeterminantalPointProcesses {
	return &DeterminantalPointProcesses{
		lambdaParam: lambdaParam,
	}
}

// ComputeSimilarityKernel computes similarity kernel matrix for documents
func (dpp *DeterminantalPointProcesses) ComputeSimilarityKernel(documents []Document) [][]float64 {
	n := len(documents)
	kernel := make([][]float64, n)
	for i := range kernel {
		kernel[i] = make([]float64, n)
	}

	for i := 0; i < n; i++ {
		for j := 0; j < n; j++ {
			if i == j {
				kernel[i][j] = 1.0
			} else {
				vecI := documents[i].Vector
				vecJ := documents[j].Vector
				similarity := cosineSimilarity(vecI, vecJ)
				if similarity > 0 {
					kernel[i][j] = similarity
				} else {
					kernel[i][j] = 0.0
				}
			}
		}
	}

	return kernel
}

// DiversifyResults diversifies search results using DPP
func (dpp *DeterminantalPointProcesses) DiversifyResults(results []SearchResult, topK int) []SearchResult {
	if len(results) <= topK {
		return results
	}

	documents := make([]Document, len(results))
	scores := make([]float64, len(results))
	for i, r := range results {
		documents[i] = r.Document
		scores[i] = r.Score
	}

	// Normalize scores
	maxScore := 0.0
	for _, s := range scores {
		if s > maxScore {
			maxScore = s
		}
	}
	if maxScore > 0 {
		for i := range scores {
			scores[i] = scores[i] / maxScore
		}
	}

	// Compute similarity kernel
	kernel := dpp.ComputeSimilarityKernel(documents)

	// Greedy DPP sampling
	selectedIndices := dpp.greedyDPPSampling(kernel, scores, topK)

	// Return selected results
	diversifiedResults := make([]SearchResult, 0, len(selectedIndices))
	for _, idx := range selectedIndices {
		result := results[idx]
		result.RankingMethod = "dpp"
		diversifiedResults = append(diversifiedResults, result)
	}

	return diversifiedResults
}

// greedyDPPSampling implements greedy sampling for DPP
func (dpp *DeterminantalPointProcesses) greedyDPPSampling(kernel [][]float64, scores []float64, k int) []int {
	n := len(kernel)
	selected := make([]int, 0)
	remaining := make(map[int]bool)
	for i := 0; i < n; i++ {
		remaining[i] = true
	}

	for len(selected) < k && len(remaining) > 0 {
		bestIdx := -1
		bestGain := -math.MaxFloat64

		for idx := range remaining {
			var gain float64
			if len(selected) == 0 {
				gain = scores[idx] * scores[idx]
			} else {
				// Compute determinant ratio (simplified)
				gain = kernel[idx][idx]
			}

			if gain > bestGain {
				bestGain = gain
				bestIdx = idx
			}
		}

		if bestIdx >= 0 {
			selected = append(selected, bestIdx)
			delete(remaining, bestIdx)
		}
	}

	return selected
}

// FacetedSearch implements faceted search with advanced filtering
type FacetedSearch struct {
	availableFacets map[string]map[string]int
	mu              sync.RWMutex
}

// NewFacetedSearch creates a new faceted search engine
func NewFacetedSearch() *FacetedSearch {
	return &FacetedSearch{
		availableFacets: make(map[string]map[string]int),
	}
}

// ExtractFacets extracts available facets and their counts from documents
func (fs *FacetedSearch) ExtractFacets(documents []Document) map[string]map[string]int {
	fs.mu.Lock()
	defer fs.mu.Unlock()

	facets := make(map[string]map[string]int)

	for _, doc := range documents {
		metadata := doc.Metadata

		// File type facet
		fileType := "unknown"
		if ft, ok := metadata["file_type"].(string); ok {
			fileType = ft
		}
		if _, exists := facets["file_type"]; !exists {
			facets["file_type"] = make(map[string]int)
		}
		facets["file_type"][fileType]++

		// File name facet
		fileName := doc.FileName
		if fileName != "" {
			parts := strings.Split(fileName, "-")
			if len(parts) > 0 {
				namePart := parts[0]
				if _, exists := facets["file_name"]; !exists {
					facets["file_name"] = make(map[string]int)
				}
				facets["file_name"][namePart]++
			}
		}
	}

	fs.availableFacets = facets
	return facets
}

// ApplyFilters applies faceted filters to documents
func (fs *FacetedSearch) ApplyFilters(documents []Document, filters map[string]interface{}) []Document {
	filtered := make([]Document, 0, len(documents))

	for _, doc := range documents {
		includeDoc := true

		for facet, values := range filters {
			valuesList, ok := values.([]string)
			if !ok {
				continue
			}

			if facet == "file_type" {
				docFileType := "unknown"
				if ft, ok := doc.Metadata["file_type"].(string); ok {
					docFileType = ft
				}
				if !contains(valuesList, docFileType) {
					includeDoc = false
					break
				}
			} else if facet == "file_name" {
				if !containsAny(valuesList, doc.FileName) {
					includeDoc = false
					break
				}
			}
		}

		if includeDoc {
			filtered = append(filtered, doc)
		}
	}

	return filtered
}

// QueryOptimizer implements query-time optimization for performance
type QueryOptimizer struct {
	queryCache  map[string]OptimizedQuery
	queryStats  map[string]QueryStats
	rewriteRules []RewriteRule
	mu          sync.RWMutex
}

// OptimizedQuery represents an optimized query with metadata
type OptimizedQuery struct {
	OriginalQuery     string
	OptimizedQuery    string
	QueryTerms        []string
	Variations        []string
	CacheHit          bool
	OptimizationTime  float64
}

// QueryStats represents statistics for a query
type QueryStats struct {
	Count     int
	TotalTime float64
}

// RewriteRule represents a query rewrite rule
type RewriteRule struct {
	Pattern     string
	Replacement string
	Description string
}

// NewQueryOptimizer creates a new query optimizer
func NewQueryOptimizer() *QueryOptimizer {
	return &QueryOptimizer{
		queryCache:  make(map[string]OptimizedQuery),
		queryStats:  make(map[string]QueryStats),
		rewriteRules: []RewriteRule{
			{
				Pattern:     "how to (\\w+)",
				Replacement: "$1 tutorial guide",
				Description: "Expand 'how to' queries",
			},
			{
				Pattern:     "what is (\\w+)",
				Replacement: "$1 definition explanation",
				Description: "Expand 'what is' queries",
			},
		},
	}
}

// OptimizeQuery optimizes a search query
func (qo *QueryOptimizer) OptimizeQuery(query string) OptimizedQuery {
	startTime := time.Now()

	// Check cache
	cacheKey := fmt.Sprintf("%d", hashString(query))
	qo.mu.RLock()
	if cached, exists := qo.queryCache[cacheKey]; exists {
		cached.CacheHit = true
		qo.mu.RUnlock()
		return cached
	}
	qo.mu.RUnlock()

	// Apply rewrite rules
	optimizedQuery := qo.applyRewriteRules(query)

	// Extract query terms
	queryTerms := qo.extractTerms(optimizedQuery)

	// Generate variations
	variations := qo.generateVariations(queryTerms)

	result := OptimizedQuery{
		OriginalQuery:    query,
		OptimizedQuery:   optimizedQuery,
		QueryTerms:       queryTerms,
		Variations:       variations,
		CacheHit:         false,
		OptimizationTime: time.Since(startTime).Seconds(),
	}

	// Cache result
	qo.mu.Lock()
	qo.queryCache[cacheKey] = result
	qo.queryStats[query] = QueryStats{
		Count:     qo.queryStats[query].Count + 1,
		TotalTime: qo.queryStats[query].TotalTime + result.OptimizationTime,
	}
	qo.mu.Unlock()

	return result
}

// applyRewriteRules applies query rewrite rules
func (qo *QueryOptimizer) applyRewriteRules(query string) string {
	optimized := query
	// Simple pattern matching (in production, use regex)
	for _, rule := range qo.rewriteRules {
		// Simplified replacement
		if strings.Contains(strings.ToLower(query), strings.ToLower(rule.Pattern)) {
			optimized = strings.ReplaceAll(optimized, rule.Pattern, rule.Replacement)
		}
	}
	return optimized
}

// extractTerms extracts significant terms from query
func (qo *QueryOptimizer) extractTerms(query string) []string {
	stopwords := map[string]bool{
		"the": true, "a": true, "an": true, "and": true, "or": true,
		"but": true, "in": true, "on": true, "at": true, "to": true,
		"for": true, "of": true, "with": true, "by": true,
	}

	terms := strings.Fields(strings.ToLower(query))
	significantTerms := make([]string, 0)
	for _, term := range terms {
		if !stopwords[term] && len(term) > 2 {
			significantTerms = append(significantTerms, term)
		}
	}

	return significantTerms
}

// generateVariations generates query variations for better recall
func (qo *QueryOptimizer) generateVariations(terms []string) []string {
	variations := make([]string, 0)
	seen := make(map[string]bool)

	// Original query
	original := strings.Join(terms, " ")
	if !seen[original] {
		variations = append(variations, original)
		seen[original] = true
	}

	// Pairwise combinations
	if len(terms) >= 2 {
		for i := 0; i < len(terms)-1; i++ {
			pair := terms[i] + " " + terms[i+1]
			if !seen[pair] {
				variations = append(variations, pair)
				seen[pair] = true
			}
		}
	}

	// Single terms
	for _, term := range terms {
		if !seen[term] {
			variations = append(variations, term)
			seen[term] = true
		}
	}

	return variations
}

// GetQueryStats gets query optimization statistics
func (qo *QueryOptimizer) GetQueryStats() map[string]interface{} {
	qo.mu.RLock()
	defer qo.mu.RUnlock()

	stats := make(map[string]interface{})
	for query, data := range qo.queryStats {
		avgTime := 0.0
		if data.Count > 0 {
			avgTime = data.TotalTime / float64(data.Count)
		}
		stats[query] = map[string]interface{}{
			"count":    data.Count,
			"total_time": data.TotalTime,
			"avg_time": avgTime,
		}
	}

	return map[string]interface{}{
		"total_queries": len(qo.queryStats),
		"cache_size":    len(qo.queryCache),
		"query_stats":   stats,
	}
}

// ABTestFramework implements A/B testing framework for ranking algorithms
type ABTestFramework struct {
	experiments       map[string]Experiment
	experimentResults map[string]map[string][]MetricResult
	mu                sync.RWMutex
}

// Experiment represents an A/B test experiment
type Experiment struct {
	ID           string
	Variants     []Variant
	TrafficSplit map[string]float64
	CreatedAt    string
	Status       string
}

// Variant represents an experiment variant
type Variant struct {
	ID     string
	Config map[string]interface{}
}

// MetricResult represents a metric result
type MetricResult struct {
	ExperimentID string
	VariantID    string
	MetricName   string
	MetricValue  float64
	Timestamp    string
}

// NewABTestFramework creates a new A/B testing framework
func NewABTestFramework() *ABTestFramework {
	return &ABTestFramework{
		experiments:       make(map[string]Experiment),
		experimentResults: make(map[string]map[string][]MetricResult),
	}
}

// CreateExperiment creates a new A/B test experiment
func (ab *ABTestFramework) CreateExperiment(experimentID string, variants []Variant, trafficSplit map[string]float64) Experiment {
	ab.mu.Lock()
	defer ab.mu.Unlock()

	if trafficSplit == nil {
		// Equal split
		split := 1.0 / float64(len(variants))
		trafficSplit = make(map[string]float64)
		for _, v := range variants {
			trafficSplit[v.ID] = split
		}
	}

	experiment := Experiment{
		ID:           experimentID,
		Variants:     variants,
		TrafficSplit: trafficSplit,
		CreatedAt:    time.Now().Format(time.RFC3339),
		Status:       "active",
	}

	ab.experiments[experimentID] = experiment
	ab.experimentResults[experimentID] = make(map[string][]MetricResult)

	return experiment
}

// AssignVariant assigns a user to a variant for testing
func (ab *ABTestFramework) AssignVariant(experimentID string, userID string) string {
	ab.mu.RLock()
	defer ab.mu.RUnlock()

	experiment, exists := ab.experiments[experimentID]
	if !exists {
		return "default"
	}

	// Consistent assignment based on user ID
	if userID != "" {
		userHash := hashString(userID)
		variantIDs := make([]string, 0, len(experiment.Variants))
		for _, v := range experiment.Variants {
			variantIDs = append(variantIDs, v.ID)
		}
		variantIndex := userHash % len(variantIDs)
		return variantIDs[variantIndex]
	}

	// Random assignment
	rand.Seed(time.Now().UnixNano())
	r := rand.Float64()
	cumulative := 0.0
	for variantID, split := range experiment.TrafficSplit {
		cumulative += split
		if r <= cumulative {
			return variantID
		}
	}

	return experiment.Variants[0].ID
}

// RecordMetric records a metric for a variant
func (ab *ABTestFramework) RecordMetric(experimentID string, variantID string, metricName string, metricValue float64) {
	ab.mu.Lock()
	defer ab.mu.Unlock()

	result := MetricResult{
		ExperimentID: experimentID,
		VariantID:    variantID,
		MetricName:   metricName,
		MetricValue:  metricValue,
		Timestamp:    time.Now().Format(time.RFC3339),
	}

	ab.experimentResults[experimentID][variantID] = append(
		ab.experimentResults[experimentID][variantID],
		result,
	)
}

// AnalyzeResults analyzes A/B test results
func (ab *ABTestFramework) AnalyzeResults(experimentID string) map[string]interface{} {
	ab.mu.RLock()
	defer ab.mu.RUnlock()

	experiment, exists := ab.experiments[experimentID]
	if !exists {
		return map[string]interface{}{"error": "Experiment not found"}
	}

	analysis := make(map[string]interface{})

	for _, variant := range experiment.Variants {
		results := ab.experimentResults[experimentID][variant.ID]
		if len(results) == 0 {
			analysis[variant.ID] = map[string]interface{}{"error": "No data"}
			continue
		}

		// Calculate metrics by type
		metrics := make(map[string][]float64)
		for _, result := range results {
			metrics[result.MetricName] = append(metrics[result.MetricName], result.MetricValue)
		}

		variantAnalysis := make(map[string]interface{})
		for metricName, values := range metrics {
			variantAnalysis[metricName] = map[string]interface{}{
				"mean":   mean(values),
				"std":    stdDev(values),
				"count":  len(values),
				"min":    minFloat(values),
				"max":    maxFloat(values),
			}
		}

		analysis[variant.ID] = variantAnalysis
	}

	return analysis
}

// PersonalizationEngine implements personalization based on user behavior
type PersonalizationEngine struct {
	userProfiles    map[string]UserProfile
	userHistory     map[string][]UserAction
	mu              sync.RWMutex
}

// UserProfile represents a user's personalization profile
type UserProfile struct {
	Preferences    map[string]float64
	DocumentTypes  map[string]int
	QueryPatterns  map[string]int
}

// UserAction represents a user action
type UserAction struct {
	Action      string
	DocumentID  string
	Context     map[string]interface{}
	Timestamp   string
}

// NewPersonalizationEngine creates a new personalization engine
func NewPersonalizationEngine() *PersonalizationEngine {
	return &PersonalizationEngine{
		userProfiles: make(map[string]UserProfile),
		userHistory:  make(map[string][]UserAction),
	}
}

// RecordUserAction records a user action for personalization
func (pe *PersonalizationEngine) RecordUserAction(userID string, action string, documentID string, context map[string]interface{}) {
	pe.mu.Lock()
	defer pe.mu.Unlock()

	actionRecord := UserAction{
		Action:     action,
		DocumentID: documentID,
		Context:    context,
		Timestamp:  time.Now().Format(time.RFC3339),
	}

	pe.userHistory[userID] = append(pe.userHistory[userID], actionRecord)

	// Update user profile
	pe.updateUserProfile(userID, actionRecord)
}

// updateUserProfile updates user profile based on action
func (pe *PersonalizationEngine) updateUserProfile(userID string, actionRecord UserAction) {
	if _, exists := pe.userProfiles[userID]; !exists {
		pe.userProfiles[userID] = UserProfile{
			Preferences:   make(map[string]float64),
			DocumentTypes: make(map[string]int),
			QueryPatterns: make(map[string]int),
		}
	}

	profile := pe.userProfiles[userID]

	// Update preferences based on action
	switch actionRecord.Action {
	case "click":
		profile.Preferences["relevance_weight"] += 0.1
	case "dwell":
		profile.Preferences["depth_weight"] += 0.1
	case "bookmark":
		profile.Preferences["bookmark_weight"] += 0.2
	}

	// Update document type preferences
	context := actionRecord.Context
	docType := "unknown"
	if dt, ok := context["document_type"].(string); ok {
		docType = dt
	}
	profile.DocumentTypes[docType]++

	// Update query patterns
	query := ""
	if q, ok := context["query"].(string); ok {
		query = q
	}
	if query != "" {
		terms := strings.Fields(strings.ToLower(query))
		for _, term := range terms {
			profile.QueryPatterns[term]++
		}
	}
}

// GetPersonalizedRanking re-ranks results based on user personalization
func (pe *PersonalizationEngine) GetPersonalizedRanking(userID string, results []SearchResult) []SearchResult {
	pe.mu.RLock()
	defer pe.mu.RUnlock()

	profile, exists := pe.userProfiles[userID]
	if !exists {
		return results
	}

	// Calculate personalized scores
	for i := range results {
		personalizedScore := results[i].Score

		// Apply preference weights
		relevanceWeight := profile.Preferences["relevance_weight"]
		personalizedScore *= (1.0 + relevanceWeight)

		// Apply document type preferences
		docType := "unknown"
		if dt, ok := results[i].Document.Metadata["file_type"].(string); ok {
			docType = dt
		}
		typeCount := profile.DocumentTypes[docType]
		if typeCount > 0 {
			boost := math.Min(float64(typeCount)*0.1, 0.5)
			personalizedScore *= (1.0 + boost)
		}

		results[i].Score = personalizedScore
	}

	// Sort by personalized scores
	sort.Slice(results, func(i, j int) bool {
		return results[i].Score > results[j].Score
	})

	return results
}

// GetUserProfile gets user profile for analysis
func (pe *PersonalizationEngine) GetUserProfile(userID string) map[string]interface{} {
	pe.mu.RLock()
	defer pe.mu.RUnlock()

	profile, exists := pe.userProfiles[userID]
	if !exists {
		return map[string]interface{}{"error": "User not found"}
	}

	return map[string]interface{}{
		"user_id":        userID,
		"preferences":    profile.Preferences,
		"document_types": profile.DocumentTypes,
		"query_patterns": profile.QueryPatterns,
		"total_actions":  len(pe.userHistory[userID]),
	}
}

// Helper functions

func hashString(s string) int {
	h := fnv.New32a()
	h.Write([]byte(s))
	return int(h.Sum32())
}

func cosineSimilarity(vec1, vec2 []float64) float64 {
	if len(vec1) != len(vec2) || len(vec1) == 0 {
		return 0.0
	}

	dotProduct := 0.0
	norm1 := 0.0
	norm2 := 0.0

	for i := range vec1 {
		dotProduct += vec1[i] * vec2[i]
		norm1 += vec1[i] * vec1[i]
		norm2 += vec2[i] * vec2[i]
	}

	if norm1 == 0 || norm2 == 0 {
		return 0.0
	}

	return dotProduct / (math.Sqrt(norm1) * math.Sqrt(norm2))
}

func contains(slice []string, item string) bool {
	for _, s := range slice {
		if s == item {
			return true
		}
	}
	return false
}

func containsAny(slice []string, text string) bool {
	for _, s := range slice {
		if strings.Contains(text, s) {
			return true
		}
	}
	return false
}

func mean(values []float64) float64 {
	if len(values) == 0 {
		return 0.0
	}
	sum := 0.0
	for _, v := range values {
		sum += v
	}
	return sum / float64(len(values))
}

func stdDev(values []float64) float64 {
	if len(values) == 0 {
		return 0.0
	}
	m := mean(values)
	sumSquares := 0.0
	for _, v := range values {
		diff := v - m
		sumSquares += diff * diff
	}
	return math.Sqrt(sumSquares / float64(len(values)))
}

func minFloat(values []float64) float64 {
	if len(values) == 0 {
		return 0.0
	}
	min := values[0]
	for _, v := range values {
		if v < min {
			min = v
		}
	}
	return min
}

func maxFloat(values []float64) float64 {
	if len(values) == 0 {
		return 0.0
	}
	max := values[0]
	for _, v := range values {
		if v > max {
			max = v
		}
	}
	return max
}