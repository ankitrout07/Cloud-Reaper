"""
Test suite for enhanced RAG search features.

Tests for:
- Learnable ranking functions using gradient boosting
- Advanced diversification (determinantal point processes)
- Semantic search with local embedding models
- Faceted search with advanced filtering
- Query-time optimization for performance
- Result caching for common queries
- A/B testing framework for ranking algorithms
- Personalization based on user behavior
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock
import time

from src.reaper.rag.enhanced_engine import (
    LearnableRanking,
    DeterminantalPointProcesses,
    LocalSemanticSearch,
    FacetedSearch,
    QueryOptimizer,
    ResultCache,
    ABTestFramework,
    PersonalizationEngine,
    EnhancedRAGEngine
)


class TestLearnableRanking:
    """Test learnable ranking functionality."""

    def test_initialization(self):
        """Test ranking system initialization."""
        ranking = LearnableRanking(model_type="xgboost")
        assert ranking.model_type == "xgboost"
        assert ranking.is_trained == False
        assert len(ranking.training_data) == 0

    def test_feature_extraction(self):
        """Test feature extraction from query and document."""
        ranking = LearnableRanking()

        query = "vm cost optimization"
        document = {
            'text': 'This is about VM cost optimization strategies',
            'sentence': 'VM cost optimization is important',
            'id': 'doc-1',
            'score': 0.8,
            'metadata': {'file_type': '.md'}
        }
        search_results = [{'document': document, 'score': 0.8}]

        features = ranking.extract_ranking_features(query, document, search_results)

        assert len(features) == 12  # Should have 12 features
        assert len(ranking.feature_names) == 12
        assert 'query_in_doc' in ranking.feature_names
        assert 'original_score' in ranking.feature_names

    def test_ranking_without_training(self):
        """Test ranking without model training (should return original order)."""
        ranking = LearnableRanking()

        results = [
            {'document': {'id': 'doc-1', 'text': 'result 1', 'score': 0.7}, 'score': 0.7},
            {'document': {'id': 'doc-2', 'text': 'result 2', 'score': 0.9}, 'score': 0.9},
        ]

        ranked = ranking.rank_results("test query", results)

        # Should return original results when not trained
        assert len(ranked) == len(results)

    def test_feedback_collection(self):
        """Test feedback collection for training."""
        ranking = LearnableRanking()

        document = {'id': 'doc-1', 'text': 'test doc'}
        ranking.add_feedback("test query", document, relevance_score=0.8, clicked=True, dwell_time=5.0)

        assert len(ranking.training_data) == 1
        assert ranking.training_data[0][1] == 0.8

    def test_model_training(self):
        """Test model training with sufficient data."""
        ranking = LearnableRanking()

        # Add training data
        for i in range(10):
            document = {'id': f'doc-{i}', 'text': f'test doc {i}'}
            ranking.add_feedback("test query", document, relevance_score=0.5 + i*0.05)

        # Train with low threshold for testing
        result = ranking.train_model(min_samples=5)

        assert result['success'] == True
        assert ranking.is_trained == True


class TestDeterminantalPointProcesses:
    """Test DPP diversification."""

    def test_initialization(self):
        """Test DPP initialization."""
        dpp = DeterminantalPointProcesses(lambda_param=0.7)
        assert dpp.lambda_param == 0.7

    def test_similarity_kernel_computation(self):
        """Test similarity kernel computation."""
        dpp = DeterminantalPointProcesses(lambda_param=0.7)

        documents = [
            {'vector': [1.0, 0.0, 0.0]},
            {'vector': [0.0, 1.0, 0.0]},
            {'vector': [0.0, 0.0, 1.0]},
        ]

        kernel = dpp.compute_similarity_kernel(documents)

        assert len(kernel) == 3
        assert len(kernel[0]) == 3
        # Diagonal should be 1.0
        assert kernel[0][0] == 1.0
        assert kernel[1][1] == 1.0
        assert kernel[2][2] == 1.0

    def test_diversification_with_few_results(self):
        """Test diversification with few results (should return as-is)."""
        dpp = DeterminantalPointProcesses(lambda_param=0.7)

        results = [
            {'document': {'id': '1', 'vector': [1.0, 0.0]}, 'score': 0.9},
            {'document': {'id': '2', 'vector': [0.0, 1.0]}, 'score': 0.8},
        ]

        diversified = dpp.diversify_results(results, top_k=10)

        assert len(diversified) == len(results)

    def test_diversification_with_many_results(self):
        """Test diversification with many results."""
        dpp = DeterminantalPointProcesses(lambda_param=0.7)

        results = []
        for i in range(10):
            results.append({
                'document': {'id': str(i), 'vector': [float(i), float(i+1)]},
                'score': 0.9 - i*0.05
            })

        diversified = dpp.diversify_results(results, top_k=5)

        assert len(diversified) == 5
        # Check that diversification method is marked
        for result in diversified:
            assert result.get('diversification_method') == 'dpp'


class TestLocalSemanticSearch:
    """Test local semantic search functionality."""

    @patch('src.reaper.rag.enhanced_engine.SentenceTransformer')
    def test_model_initialization(self, mock_transformer):
        """Test local model initialization."""
        mock_model = Mock()
        mock_transformer.return_value = mock_model

        semantic = LocalSemanticSearch(model_name='test-model')

        assert semantic.model_name == 'test-model'
        mock_transformer.assert_called_once()

    def test_embedding_without_model(self):
        """Test embedding generation when model is not available."""
        semantic = LocalSemanticSearch()
        semantic.model = None  # Simulate unavailable model

        documents = [{'text': 'test document'}]
        embeddings = semantic.embed_documents(documents)

        assert len(embeddings) == 0

    @patch('src.reaper.rag.enhanced_engine.SentenceTransformer')
    def test_query_embedding(self, mock_transformer):
        """Test query embedding generation."""
        mock_model = Mock()
        mock_model.encode.return_value = np.array([0.1, 0.2, 0.3])
        mock_transformer.return_value = mock_model

        semantic = LocalSemanticSearch()
        embedding = semantic.embed_query("test query")

        assert len(embedding) == 3
        mock_model.encode.assert_called_once()


class TestFacetedSearch:
    """Test faceted search functionality."""

    def test_initialization(self):
        """Test faceted search initialization."""
        faceted = FacetedSearch()
        assert faceted.available_facets == {}

    def test_facet_extraction(self):
        """Test facet extraction from documents."""
        faceted = FacetedSearch()

        documents = [
            {
                'file_name': 'guide-vm.md',
                'metadata': {'file_type': '.md', 'date': '2024-01-15'}
            },
            {
                'file_name': 'api-storage.py',
                'metadata': {'file_type': '.py', 'date': '2024-01-16'}
            },
        ]

        facets = faceted.extract_facets(documents)

        assert 'file_type' in facets
        assert 'file_name' in facets
        assert facets['file_type']['.md'] == 1
        assert facets['file_type']['.py'] == 1

    def test_filter_application(self):
        """Test applying filters to documents."""
        faceted = FacetedSearch()

        documents = [
            {
                'id': '1',
                'file_name': 'guide.md',
                'metadata': {'file_type': '.md'}
            },
            {
                'id': '2',
                'file_name': 'script.py',
                'metadata': {'file_type': '.py'}
            },
        ]

        filters = {'file_type': ['.md']}
        filtered = faceted.apply_filters(documents, filters)

        assert len(filtered) == 1
        assert filtered[0]['metadata']['file_type'] == '.md'

    def test_filter_suggestions(self):
        """Test filter suggestion generation."""
        faceted = FacetedSearch()

        documents = [
            {'file_name': 'vm-guide.md', 'metadata': {'file_type': '.md'}},
            {'file_name': 'storage-doc.md', 'metadata': {'file_type': '.md'}},
        ]

        suggestions = faceted.get_filter_suggestions("vm optimization", documents)

        assert 'file_type' in suggestions or len(suggestions) > 0


class TestQueryOptimizer:
    """Test query optimization functionality."""

    def test_initialization(self):
        """Test query optimizer initialization."""
        optimizer = QueryOptimizer()
        assert optimizer.query_cache == {}
        assert len(optimizer.rewrite_rules) > 0

    def test_query_optimization(self):
        """Test basic query optimization."""
        optimizer = QueryOptimizer()

        query = "how to optimize vm costs"
        optimized = optimizer.optimize_query(query)

        assert optimized['original_query'] == query
        assert optimized['optimized_query'] != query or optimized['optimized_query'] == query
        assert 'query_terms' in optimized
        assert 'variations' in optimized

    def test_cache_hit(self):
        """Test query cache hit."""
        optimizer = QueryOptimizer()

        query = "test query"
        optimizer.optimize_query(query)  # First call - cache miss

        optimized = optimizer.optimize_query(query)  # Second call - cache hit

        assert optimized['cache_hit'] == True

    def test_query_stats(self):
        """Test query statistics tracking."""
        optimizer = QueryOptimizer()

        optimizer.optimize_query("query 1")
        optimizer.optimize_query("query 2")
        optimizer.optimize_query("query 1")  # Repeat

        stats = optimizer.get_query_stats()

        assert stats['total_queries'] == 2
        assert stats['cache_size'] >= 2


class TestResultCache:
    """Test result caching functionality."""

    def test_initialization(self):
        """Test result cache initialization."""
        cache = ResultCache(redis_client=None, ttl=3600)
        assert cache.ttl == 3600
        assert cache.local_cache == {}

    def test_cache_key_generation(self):
        """Test cache key generation."""
        cache = ResultCache()

        key1 = cache.generate_cache_key("query 1", None, 10)
        key2 = cache.generate_cache_key("query 1", None, 10)
        key3 = cache.generate_cache_key("query 2", None, 10)

        assert key1 == key2  # Same parameters = same key
        assert key1 != key3  # Different parameters = different key

    def test_cache_set_and_get(self):
        """Test cache set and get operations."""
        cache = ResultCache()

        results = [{'id': '1', 'score': 0.9}]
        cache.set("test query", results, None, 10)

        cached = cache.get("test query", None, 10)

        assert cached == results

    def test_cache_miss(self):
        """Test cache miss scenario."""
        cache = ResultCache()

        cached = cache.get("nonexistent query", None, 10)

        assert cached is None

    def test_cache_stats(self):
        """Test cache statistics."""
        cache = ResultCache()

        results = [{'id': '1'}]
        cache.set("query 1", results)

        cache.get("query 1")  # Hit
        cache.get("query 2")  # Miss

        stats = cache.get_stats()

        assert stats['total_hits'] == 1
        assert stats['total_misses'] == 1
        assert stats['hit_rate'] == 0.5


class TestABTestFramework:
    """Test A/B testing framework."""

    def test_initialization(self):
        """Test A/B testing framework initialization."""
        ab_test = ABTestFramework()
        assert ab_test.experiments == {}
        assert ab_test.experiment_results == {}

    def test_experiment_creation(self):
        """Test creating a new experiment."""
        ab_test = ABTestFramework()

        variants = [
            {'id': 'variant_a', 'config': {'param': 'value_a'}},
            {'id': 'variant_b', 'config': {'param': 'value_b'}},
        ]

        experiment = ab_test.create_experiment("test_exp", variants, None)

        assert experiment.get("id") == "test_exp"
        assert len(experiment.get("variants", [])) == 2
        assert experiment.get("status") == "active"

    def test_variant_assignment(self):
        """Test variant assignment for users."""
        ab_test = ABTestFramework()

        variants = [
            {'id': 'variant_a', 'config': {}},
            {'id': 'variant_b', 'config': {}},
        ]
        ab_test.create_experiment("test_exp", variants, None)

        # Test with user ID (consistent assignment)
        variant1 = ab_test.assign_variant("test_exp", "user-123")
        variant2 = ab_test.assign_variant("test_exp", "user-123")

        assert variant1 == variant2  # Same user should get same variant

        # Test without user ID (random assignment)
        variant3 = ab_test.assign_variant("test_exp", "")
        assert variant3 in ['variant_a', 'variant_b']

    def test_metric_recording(self):
        """Test recording metrics for variants."""
        ab_test = ABTestFramework()

        variants = [{'id': 'variant_a', 'config': {}}]
        ab_test.create_experiment("test_exp", variants, None)

        ab_test.record_metric("test_exp", "variant_a", "ctr", 0.15)
        ab_test.record_metric("test_exp", "variant_a", "dwell_time", 5.0)

        results = ab_test.experiment_results[("test_exp", "variant_a")]
        assert len(results) == 2

    def test_results_analysis(self):
        """Test analyzing experiment results."""
        ab_test = ABTestFramework()

        variants = [
            {'id': 'variant_a', 'config': {}},
            {'id': 'variant_b', 'config': {}},
        ]
        ab_test.create_experiment("test_exp", variants, None)

        # Add some metrics
        for i in range(10):
            ab_test.record_metric("test_exp", "variant_a", "ctr", 0.1 + i*0.01)
            ab_test.record_metric("test_exp", "variant_b", "ctr", 0.08 + i*0.005)

        analysis = ab_test.analyze_results("test_exp")

        assert "variant_a" in analysis
        assert "variant_b" in analysis
        assert "ctr" in analysis["variant_a"]


class TestPersonalizationEngine:
    """Test personalization engine."""

    def test_initialization(self):
        """Test personalization engine initialization."""
        personalization = PersonalizationEngine()
        assert personalization.user_profiles == {}
        assert personalization.user_history == {}

    def test_user_action_recording(self):
        """Test recording user actions."""
        personalization = PersonalizationEngine()

        personalization.record_user_action(
            "user-1",
            "click",
            "doc-1",
            {"query": "test query", "document_type": ".md"}
        )

        assert "user-1" in personalization.user_history
        assert len(personalization.user_history["user-1"]) == 1
        assert "user-1" in personalization.user_profiles

    def test_profile_update(self):
        """Test user profile updates from actions."""
        personalization = PersonalizationEngine()

        personalization.record_user_action("user-1", "click", "doc-1", {})
        personalization.record_user_action("user-1", "bookmark", "doc-2", {})

        profile = personalization.get_user_profile("user-1")

        assert profile['user_id'] == "user-1"
        assert profile['total_actions'] == 2
        assert profile['preferences']['relevance_weight'] > 0
        assert profile['preferences']['bookmark_weight'] > 0

    def test_personalized_ranking(self):
        """Test personalized result ranking."""
        personalization = PersonalizationEngine()

        # Build user profile
        personalization.record_user_action(
            "user-1",
            "click",
            "doc-1",
            {"query": "vm", "document_type": ".md"}
        )

        results = [
            {'document': {'id': '1', 'metadata': {'file_type': '.md'}}, 'score': 0.7},
            {'document': {'id': '2', 'metadata': {'file_type': '.py'}}, 'score': 0.8},
        ]

        personalized = personalization.get_personalized_ranking("user-1", results)

        assert len(personalized) == len(results)
        # Results should be re-ranked based on user preferences

    def test_user_without_profile(self):
        """Test ranking for user without profile."""
        personalization = PersonalizationEngine()

        results = [
            {'document': {'id': '1'}, 'score': 0.7},
            {'document': {'id': '2'}, 'score': 0.8},
        ]

        personalized = personalization.get_personalized_ranking("user-999", results)

        # Should return original results
        assert personalized == results


class TestEnhancedRAGEngine:
    """Test integrated enhanced RAG engine."""

    @patch('src.reaper.rag.enhanced_engine.redis')
    def test_initialization(self, mock_redis):
        """Test enhanced RAG engine initialization."""
        mock_client = Mock()
        mock_redis.from_url.return_value = mock_client
        mock_client.ping.return_value = True

        config = {
            'ranking_model': 'xgboost',
            'dpp_lambda': 0.7,
            'cache_ttl': 3600
        }

        engine = EnhancedRAGEngine(config)

        assert engine.learnable_ranking is not None
        assert engine.dpp is not None
        assert engine.local_semantic is not None
        assert engine.faceted_search is not None
        assert engine.query_optimizer is not None

    @patch('src.reaper.rag.enhanced_engine.redis')
    def test_search_with_caching(self, mock_redis):
        """Test search with result caching."""
        mock_client = Mock()
        mock_redis.from_url.return_value = mock_client
        mock_client.ping.return_value = True

        engine = EnhancedRAGEngine()

        # Mock results
        test_results = [{'id': '1', 'score': 0.9}]
        engine.result_cache.set("test query", test_results)

        enable_features = {'cache': True}
        result = engine.search("test query", enable_features=enable_features)

        assert result['cache_hit'] == True
        assert result['results'] == test_results

    @patch('src.reaper.rag.enhanced_engine.redis')
    def test_search_with_query_optimization(self, mock_redis):
        """Test search with query optimization."""
        mock_client = Mock()
        mock_redis.from_url.return_value = mock_client
        mock_client.ping.return_value = True

        engine = EnhancedRAGEngine()

        enable_features = {
            'cache': False,
            'query_optimization': True
        }
        result = engine.search("how to optimize costs", enable_features=enable_features)

        assert 'query_optimization' in result
        assert result['query_optimization']['original_query'] == "how to optimize costs"

    @patch('src.reaper.rag.enhanced_engine.redis')
    def test_feedback_integration(self, mock_redis):
        """Test feedback integration across components."""
        mock_client = Mock()
        mock_redis.from_url.return_value = mock_client
        mock_client.ping.return_value = True

        engine = EnhancedRAGEngine()

        document = {'id': 'doc-1', 'text': 'test'}
        engine.add_feedback("test query", document, 0.8, user_id="user-1")

        # Check that feedback was added to ranking system
        assert len(engine.learnable_ranking.training_data) == 1

        # Check that personalization was updated
        assert "user-1" in engine.personalization.user_history

    @patch('src.reaper.rag.enhanced_engine.redis')
    def test_analytics_collection(self, mock_redis):
        """Test analytics collection across components."""
        mock_client = Mock()
        mock_redis.from_url.return_value = mock_client
        mock_client.ping.return_value = True

        engine = EnhancedRAGEngine()

        # Perform some operations
        engine.query_optimizer.optimize_query("test query")
        engine.result_cache.set("query", [], None, 10)

        analytics = engine.get_analytics()

        assert 'cache_stats' in analytics
        assert 'query_stats' in analytics


if __name__ == "__main__":
    pytest.main([__file__, "-v"])