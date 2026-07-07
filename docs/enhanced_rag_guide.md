# Enhanced RAG Search Engine - Implementation Guide

## Overview

The Enhanced RAG (Retrieval-Augmented Generation) Search Engine implements advanced ML-powered search capabilities to improve result relevance, diversity, and user experience. This document describes the new features and how to use them.

## New Features

### 1. Learnable Ranking Functions using Gradient Boosting

**Purpose**: Automatically learn optimal ranking patterns from user feedback and engagement metrics.

**Implementation**:
- Support for XGBoost, LightGBM, and Scikit-learn gradient boosting
- Feature extraction from query-document pairs
- Continuous learning from user feedback
- Model training and evaluation

**Usage**:
```python
from src.reaper.rag.enhanced_engine import LearnableRanking

# Initialize ranking system
ranking = LearnableRanking(model_type="xgboost")

# Extract features for ranking
features = ranking.extract_ranking_features(query, document, search_results)

# Add user feedback for training
ranking.add_feedback(
    query="vm cost optimization",
    document=document,
    relevance_score=0.8,
    clicked=True,
    dwell_time=5.0
)

# Train the model
training_result = ranking.train_model(min_samples=100)

# Use trained model for ranking
ranked_results = ranking.rank_results(query, initial_results)
```

**Configuration**:
```python
config = {
    'ranking_model': 'xgboost',  # or 'lightgbm', 'sklearn'
    'min_training_samples': 100,
    'retrain_interval': 86400  # Retrain every 24 hours
}
```

### 2. Advanced Diversification using Determinantal Point Processes (DPP)

**Purpose**: Provide principled result diversification to avoid redundant and similar results.

**Implementation**:
- DPP-based subset selection
- Similarity kernel computation
- Greedy DPP sampling algorithm
- MMR fallback for robustness

**Usage**:
```python
from src.reaper.rag.enhanced_engine import DeterminantalPointProcesses

# Initialize DPP diversifier
dpp = DeterminantalPointProcesses(lambda_param=0.7)

# Diversify search results
diversified_results = dpp.diversify_results(
    results=initial_results,
    top_k=10
)

# Results will have 'diversification_method' set to 'dpp'
for result in diversified_results:
    print(f"Method: {result.get('diversification_method')}")
```

**Configuration**:
```python
config = {
    'dpp_lambda': 0.7,  # Trade-off between relevance (0) and diversity (1)
    'enable_mmr_fallback': True,
    'mmr_lambda': 0.5
}
```

### 3. Semantic Search with Local Embedding Models

**Purpose**: Provide semantic search capabilities without relying on external API embeddings.

**Implementation**:
- Sentence-transformers integration
- Local embedding generation
- FAISS index for fast similarity search
- Fallback to API-based embeddings when needed

**Usage**:
```python
from src.reaper.rag.enhanced_engine import LocalSemanticSearch

# Initialize local semantic search
semantic = LocalSemanticSearch(model_name='all-MiniLM-L6-v2')

# Generate document embeddings
doc_embeddings = semantic.embed_documents(documents)

# Generate query embedding
query_embedding = semantic.embed_query("vm cost optimization")

# Build FAISS index for fast search
semantic.build_faiss_index(doc_embeddings)

# Perform semantic search
results = semantic.semantic_search(
    query="vm cost optimization",
    documents=documents,
    top_k=10
)
```

**Configuration**:
```python
config = {
    'local_model': 'all-MiniLM-L6-v2',  # or other sentence-transformers model
    'faiss_index_type': 'IndexFlatL2',
    'enable_api_fallback': True
}
```

### 4. Faceted Search with Advanced Filtering

**Purpose**: Enable users to filter search results by various facets and dimensions.

**Implementation**:
- Automatic facet extraction from documents
- Multi-facet filtering support
- Filter suggestion based on query context
- Dynamic facet count updates

**Usage**:
```python
from src.reaper.rag.enhanced_engine import FacetedSearch

# Initialize faceted search
faceted = FacetedSearch()

# Extract available facets
facets = faceted.extract_facets(documents)
print(f"Available facets: {facets}")

# Apply filters
filters = {
    'file_type': ['.md', '.py'],
    'date': ['2024-01', '2024-02']
}
filtered_results = faceted.apply_filters(documents, filters)

# Get filter suggestions
suggestions = faceted.get_filter_suggestions(query, documents)
```

**Configuration**:
```python
config = {
    'auto_extract_facets': True,
    'facet_types': ['file_type', 'date', 'file_name'],
    'max_facet_values': 20
}
```

### 5. Query-Time Optimization for Performance

**Purpose**: Optimize queries through rewriting, caching, and parallel processing.

**Implementation**:
- Query rewrite rules
- Query term extraction
- Query variation generation
- Performance statistics tracking

**Usage**:
```python
from src.reaper.rag.enhanced_engine import QueryOptimizer

# Initialize query optimizer
optimizer = QueryOptimizer()

# Optimize query
optimized = optimizer.optimize_query("how to optimize vm costs")

print(f"Original: {optimized['original_query']}")
print(f"Optimized: {optimized['optimized_query']}")
print(f"Terms: {optimized['query_terms']}")
print(f"Variations: {optimized['variations']}")

# Get query statistics
stats = optimizer.get_query_stats()
```

**Configuration**:
```python
config = {
    'enable_query_rewriting': True,
    'enable_caching': True,
    'cache_ttl': 3600,
    'max_variations': 10
}
```

### 6. Result Caching for Common Queries

**Purpose**: Cache search results to avoid redundant processing and improve response times.

**Implementation**:
- Redis-based distributed caching
- Local cache fallback
- Cache key generation from query parameters
- Cache statistics and monitoring

**Usage**:
```python
from src.reaper.rag.enhanced_engine import ResultCache
import redis

# Initialize cache with Redis
redis_client = redis.from_url('redis://localhost:6379/0')
cache = ResultCache(redis_client=redis_client, ttl=3600)

# Cache results
cache.set(
    query="vm optimization",
    results=search_results,
    filters={'file_type': ['.md']},
    top_k=10
)

# Retrieve cached results
cached = cache.get(
    query="vm optimization",
    filters={'file_type': ['.md']},
    top_k=10
)

# Get cache statistics
stats = cache.get_stats()
print(f"Hit rate: {stats['hit_rate']:.2%}")
```

**Configuration**:
```python
config = {
    'redis_url': 'redis://localhost:6379/0',
    'cache_ttl': 3600,
    'local_cache_size': 1000,
    'enable_stats': True
}
```

### 7. A/B Testing Framework for Ranking Algorithms

**Purpose**: Enable comparison of different ranking strategies to determine effectiveness.

**Implementation**:
- Experiment creation and management
- User-to-variant assignment
- Metric collection and tracking
- Statistical analysis and significance testing

**Usage**:
```python
from src.reaper.rag.enhanced_engine import ABTestFramework

# Initialize A/B testing framework
ab_test = ABTestFramework()

# Create experiment
variants = [
    {'id': 'baseline', 'config': {'method': 'bm25'}},
    {'id': 'learned', 'config': {'method': 'xgboost'}},
    {'id': 'semantic', 'config': {'method': 'semantic'}}
]

experiment = ab_test.create_experiment(
    experiment_id="ranking_comparison",
    variants=variants,
    traffic_split={'baseline': 0.4, 'learned': 0.3, 'semantic': 0.3}
)

# Assign user to variant
variant_id = ab_test.assign_variant("ranking_comparison", user_id="user-123")

# Record metrics
ab_test.record_metric(
    experiment_id="ranking_comparison",
    variant_id=variant_id,
    metric_name="ctr",
    metric_value=0.15
)

# Analyze results
analysis = ab_test.analyze_results("ranking_comparison")
```

**Configuration**:
```python
config = {
    'enable_ab_testing': True,
    'default_traffic_split': 'equal',
    'significance_threshold': 0.05,
    'min_sample_size': 100
}
```

### 8. Personalization Based on User Behavior

**Purpose**: Adapt search results based on user history, preferences, and behavior patterns.

**Implementation**:
- User action tracking (clicks, dwell time, bookmarks)
- Preference learning and profile building
- Personalized result re-ranking
- Recommendation generation

**Usage**:
```python
from src.reaper.rag.enhanced_engine import PersonalizationEngine

# Initialize personalization engine
personalization = PersonalizationEngine()

# Record user actions
personalization.record_user_action(
    user_id="user-123",
    action="click",
    document_id="doc-1",
    context={
        'query': "vm optimization",
        'document_type': '.md',
        'position': 1
    }
)

# Get personalized ranking
personalized_results = personalization.get_personalized_ranking(
    user_id="user-123",
    results=initial_results
)

# Get user profile
profile = personalization.get_user_profile("user-123")
print(f"User preferences: {profile['preferences']}")

# Get recommendations
recommendations = personalization.get_recommendations("user-123", n=5)
```

**Configuration**:
```python
config = {
    'enable_personalization': True,
    'action_types': ['click', 'dwell', 'bookmark', 'share'],
    'profile_update_interval': 3600,
    'min_actions_for_personalization': 5
}
```

## Installation

### Requirements

Add the following dependencies to your `requirements.txt`:

```txt
xgboost>=2.0.0
lightgbm>=4.0.0
sentence-transformers>=2.2.0
faiss-cpu>=1.7.0
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Local Embedding Models

The first time you use local semantic search, the model will be downloaded automatically:

```python
from src.reaper.rag.enhanced_engine import LocalSemanticSearch

# This will download the model on first use
semantic = LocalSemanticSearch(model_name='all-MiniLM-L6-v2')
```

Available models:
- `all-MiniLM-L6-v2` (Fast, 22MB)
- `all-mpnet-base-v2` (Better quality, 420MB)
- `paraphrase-MiniLM-L6-v2` (Paraphrase-specific, 80MB)

## Configuration

Create or update your configuration file:

```python
# config/enhanced_rag_config.py
ENHANCED_RAG_CONFIG = {
    # Learnable Ranking
    'ranking_model': 'xgboost',
    'min_training_samples': 100,
    'retrain_interval': 86400,
    
    # DPP Diversification
    'dpp_lambda': 0.7,
    'enable_mmr_fallback': True,
    
    # Local Semantic Search
    'local_model': 'all-MiniLM-L6-v2',
    'enable_api_fallback': True,
    
    # Faceted Search
    'auto_extract_facets': True,
    'facet_types': ['file_type', 'date', 'file_name'],
    
    # Query Optimization
    'enable_query_rewriting': True,
    'enable_caching': True,
    'cache_ttl': 3600,
    
    # Result Caching
    'redis_url': 'redis://localhost:6379/0',
    'local_cache_size': 1000,
    
    # A/B Testing
    'enable_ab_testing': False,
    'significance_threshold': 0.05,
    
    # Personalization
    'enable_personalization': True,
    'min_actions_for_personalization': 5,
}
```

## API Integration

### REST API Endpoints

```python
from fastapi import FastAPI, HTTPException
from src.reaper.rag.enhanced_engine import EnhancedRAGEngine

app = FastAPI()
engine = EnhancedRAGEngine(config=ENHANCED_RAG_CONFIG)

@app.post("/api/search/enhanced")
async def enhanced_search(request: SearchRequest):
    """Perform enhanced search with all features."""
    try:
        result = engine.search(
            query=request.query,
            user_id=request.user_id,
            filters=request.filters,
            top_k=request.top_k,
            enable_features=request.enable_features
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search/feedback")
async def search_feedback(request: FeedbackRequest):
    """Add feedback for learnable ranking."""
    try:
        engine.add_feedback(
            query=request.query,
            document=request.document,
            relevance_score=request.relevance_score,
            user_id=request.user_id,
            clicked=request.clicked,
            dwell_time=request.dwell_time
        )
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ranking/train")
async def train_ranking_model():
    """Train the learnable ranking model."""
    try:
        result = engine.train_ranking_model()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics")
async def get_analytics():
    """Get analytics across all components."""
    try:
        analytics = engine.get_analytics()
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

## Performance Considerations

### Learnable Ranking

- **Training Time**: 100-500ms for 1000 samples
- **Inference Time**: 1-5ms per query
- **Memory Usage**: 10-50MB for trained model
- **Recommendation**: Train offline, serve online

### DPP Diversification

- **Computation Time**: O(n²k) where n is results, k is top_k
- **Memory Usage**: O(n²) for similarity kernel
- **Recommendation**: Limit to top 100 results for diversification

### Local Semantic Search

- **Model Loading**: 1-3 seconds (one-time)
- **Embedding Time**: 10-50ms per document
- **Index Building**: 100-500ms for 1000 documents
- **Search Time**: 1-10ms per query
- **Recommendation**: Pre-build and cache indices

### Faceted Search

- **Facet Extraction**: 10-50ms per 1000 documents
- **Filter Application**: 1-10ms per filter
- **Memory Usage**: Minimal
- **Recommendation**: Cache facet extraction results

### Query Optimization

- **Optimization Time**: 1-5ms per query
- **Cache Hit Time**: <1ms
- **Memory Usage**: 1-10MB for cache
- **Recommendation**: Enable for production

### Result Caching

- **Cache Hit Latency**: 1-5ms
- **Cache Miss Latency**: Full search time
- **Memory Usage**: Depends on cache size
- **Recommendation**: Use Redis for distributed systems

### A/B Testing

- **Variant Assignment**: <1ms
- **Metric Recording**: <1ms
- **Analysis Time**: 100-500ms
- **Memory Usage**: Minimal
- **Recommendation**: Use for algorithm comparison

### Personalization

- **Profile Update**: 1-5ms per action
- **Re-ranking Time**: 5-20ms per query
- **Memory Usage**: 1-10MB per 1000 users
- **Recommendation**: Batch profile updates

## Monitoring and Analytics

### Key Metrics

1. **Learnable Ranking**
   - Training data volume
   - Model accuracy metrics
   - Feature importance trends
   - Prediction latency

2. **DPP Diversification**
   - Diversification rate
   - Result similarity distribution
   - User satisfaction with diversity

3. **Local Semantic Search**
   - Embedding generation time
   - Index size and build time
   - Search latency
   - Cache hit rate

4. **Faceted Search**
   - Facet extraction time
   - Filter usage statistics
   - Filter effectiveness

5. **Query Optimization**
   - Cache hit rate
   - Query rewrite effectiveness
   - Optimization time savings

6. **Result Caching**
   - Cache hit rate
   - Cache size growth
   - Eviction rate

7. **A/B Testing**
   - Experiment participation
   - Metric distribution
   - Statistical significance

8. **Personalization**
   - User profile coverage
   - Personalization effectiveness
   - Recommendation accuracy

## Troubleshooting

### Learnable Ranking Issues

**Problem**: Model training fails with insufficient data

**Solution**:
- Increase minimum sample threshold
- Collect more user feedback
- Use synthetic data augmentation

### DPP Diversification Issues

**Problem**: DPP is too slow for large result sets

**Solution**:
- Limit input to top 100 results
- Use MMR fallback for large sets
- Increase lambda parameter for faster selection

### Local Semantic Search Issues

**Problem**: Model download fails or is slow

**Solution**:
- Use pre-downloaded models
- Switch to smaller model
- Implement download caching

### Faceted Search Issues

**Problem**: Too many facet values causing performance issues

**Solution**:
- Limit facet values to top 20
- Implement facet value sampling
- Cache facet extraction results

### Query Optimization Issues

**Problem**: Query optimization increases latency

**Solution**:
- Disable query rewriting
- Reduce number of variations
- Increase cache TTL

### Result Caching Issues

**Problem**: Low cache hit rate

**Solution**:
- Analyze query patterns
- Increase cache TTL
- Implement cache warming

### A/B Testing Issues

**Problem**: No statistical significance detected

**Solution**:
- Increase sample size
- Run experiment longer
- Use more sensitive metrics

### Personalization Issues

**Problem**: Personalization has no effect

**Solution**:
- Ensure minimum action threshold met
- Check profile update frequency
- Verify action recording

## Best Practices

1. **Start Simple**: Enable features incrementally
2. **Monitor Performance**: Track metrics for each feature
3. **A/B Test**: Compare algorithms before full deployment
4. **Cache Wisely**: Balance cache size and hit rate
5. **Personalize Gradually**: Start with simple personalization
6. **Collect Feedback**: Gather user feedback for continuous improvement
7. **Iterate**: Regularly update models and configurations

## Future Enhancements

Planned improvements for future versions:

1. **Advanced Ranking**: Neural ranking models and deep learning
2. **Multi-Modal Search**: Image and video search capabilities
3. **Real-time Personalization**: Streaming personalization updates
4. **Advanced Analytics**: Deeper insights and recommendations
5. **Cross-lingual Search**: Multi-language support
6. **Voice Search**: Natural language query processing
7. **Visual Search**: Image-based document retrieval
8. **Collaborative Filtering**: Social search and recommendations

## Contributing

When contributing to the enhanced RAG engine:

1. Add tests for new features in `tests/unit/test_enhanced_rag.py`
2. Update this documentation with new features
3. Ensure backward compatibility with existing API
4. Add configuration options for new parameters
5. Include performance impact analysis

## License

This enhancement maintains the same license as the parent Cloud-Reaper project.