"""
Enhanced RAG Search Engine with Advanced ML Features

This module implements advanced retrieval-augmented generation capabilities including:
- Learnable ranking functions using gradient boosting
- Advanced diversification using determinantal point processes
- Semantic search with local embedding models
- Faceted search with advanced filtering
- Query-time optimization for performance
- Result caching for common queries
- A/B testing framework for ranking algorithms
- Personalization based on user behavior
"""

import hashlib
import json
import os
import pickle
import random
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from functools import lru_cache

import numpy as np
import redis
import xgboost as xgb
from sentence_transformers import SentenceTransformer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler
import faiss

from reaper.utils.error_handler import get_logger

logger = get_logger(__name__)


class LearnableRanking:
    """
    Learnable ranking functions using gradient boosting for optimal result ranking.
    
    Uses ML models to learn optimal ranking based on user feedback and engagement metrics.
    """

    def __init__(self, model_type: str = "xgboost"):
        """
        Initialize the learnable ranking system.
        
        Args:
            model_type: Type of model to use ('xgboost' or 'lightgbm' or 'sklearn')
        """
        self.model_type = model_type
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = []
        self.is_trained = False
        
        # Training data storage
        self.training_data = []
        self.feedback_history = []
        
        # Initialize model
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize the ranking model based on type."""
        if self.model_type == "xgboost":
            self.model = xgb.XGBRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                objective='reg:squarederror',
                random_state=42
            )
        elif self.model_type == "lightgbm":
            try:
                import lightgbm as lgb
                self.model = lgb.LGBMRegressor(
                    n_estimators=100,
                    max_depth=6,
                    learning_rate=0.1,
                    random_state=42
                )
            except ImportError:
                logger.warning("LightGBM not available, falling back to XGBoost")
                self.model = xgb.XGBRegressor(
                    n_estimators=100,
                    max_depth=6,
                    learning_rate=0.1,
                    objective='reg:squarederror',
                    random_state=42
                )
        else:  # sklearn
            self.model = GradientBoostingRegressor(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=42
            )
    
    def extract_ranking_features(self, query: str, document: Dict, search_results: List[Dict]) -> np.ndarray:
        """
        Extract features for ranking from query, document, and search context.
        
        Args:
            query: Search query
            document: Document to rank
            search_results: All search results for context
            
        Returns:
            Feature vector for ranking
        """
        features = []
        
        # Text similarity features
        query_lower = query.lower()
        doc_text = document.get('text', '').lower()
        doc_sentence = document.get('sentence', '').lower()
        
        # Exact match features
        features.append(float(query_lower in doc_text))  # Query in document
        features.append(float(query_lower in doc_sentence))  # Query in sentence
        
        # Length features
        features.append(len(doc_text))  # Document length
        features.append(len(doc_sentence))  # Sentence length
        features.append(len(query))  # Query length
        
        # Position features
        doc_index = -1
        for i, result in enumerate(search_results):
            if result.get('document', {}).get('id') == document.get('id'):
                doc_index = i
                break
        features.append(doc_index if doc_index >= 0 else len(search_results))
        
        # Score features
        original_score = document.get('score', 0.0)
        features.append(original_score)
        
        # Context features
        avg_score = np.mean([r.get('score', 0.0) for r in search_results]) if search_results else 0.0
        features.append(original_score - avg_score)  # Score relative to average
        
        # Document metadata features
        metadata = document.get('metadata', {})
        features.append(len(metadata))  # Metadata richness
        
        # File type features
        file_type = metadata.get('file_type', '')
        features.append(hash(file_type) % 100)  # Encoded file type
        
        # Text complexity features
        words = doc_text.split()
        features.append(len(words))  # Word count
        features.append(len(set(words)) / max(len(words), 1))  # Unique word ratio
        
        self.feature_names = [
            'query_in_doc', 'query_in_sentence',
            'doc_length', 'sentence_length', 'query_length',
            'doc_position', 'original_score', 'relative_score',
            'metadata_count', 'file_type_encoded',
            'word_count', 'unique_word_ratio'
        ]
        
        return np.array(features)
    
    def rank_results(self, query: str, results: List[Dict]) -> List[Dict]:
        """
        Rank search results using the learned model.
        
        Args:
            query: Search query
            results: Initial search results to rank
            
        Returns:
            Re-ranked results
        """
        if not self.is_trained or not results:
            # Return original results if model not trained
            return results
        
        try:
            # Extract features for each result
            features = []
            for result in results:
                document = result.get('document', result)
                feature_vector = self.extract_ranking_features(query, document, results)
                features.append(feature_vector)
            
            if not features:
                return results
            
            # Scale features
            features_array = np.array(features)
            scaled_features = self.scaler.transform(features_array)
            
            # Predict scores
            predicted_scores = self.model.predict(scaled_features)
            
            # Update results with predicted scores
            for i, result in enumerate(results):
                result['learned_score'] = float(predicted_scores[i])
                result['ranking_method'] = f'learnable_{self.model_type}'
            
            # Sort by predicted scores
            ranked_results = sorted(results, key=lambda x: x.get('learned_score', 0), reverse=True)
            
            return ranked_results
            
        except Exception as e:
            logger.error(f"Learnable ranking failed: {e}")
            return results
    
    def add_feedback(self, query: str, document: Dict, relevance_score: float, 
                    clicked: bool = False, dwell_time: float = 0.0):
        """
        Add user feedback for training.
        
        Args:
            query: Search query
            document: Document that was rated
            relevance_score: User-provided relevance score (0-1)
            clicked: Whether the user clicked on the result
            dwell_time: Time spent on the result (seconds)
        """
        feedback = {
            'query': query,
            'document': document,
            'relevance_score': relevance_score,
            'clicked': clicked,
            'dwell_time': dwell_time,
            'timestamp': datetime.now().isoformat()
        }
        
        self.feedback_history.append(feedback)
        
        # Extract features for training
        features = self.extract_ranking_features(query, document, [document])
        self.training_data.append((features, relevance_score))
    
    def train_model(self, min_samples: int = 100) -> Dict[str, Any]:
        """
        Train the ranking model on collected feedback.
        
        Args:
            min_samples: Minimum number of samples required for training
            
        Returns:
            Training statistics
        """
        if len(self.training_data) < min_samples:
            return {
                'success': False,
                'error': f'Insufficient training data: {len(self.training_data)} < {min_samples}'
            }
        
        try:
            # Prepare training data
            X = np.array([item[0] for item in self.training_data])
            y = np.array([item[1] for item in self.training_data])
            
            # Scale features
            X_scaled = self.scaler.fit_transform(X)
            
            # Train model
            self.model.fit(X_scaled, y)
            self.is_trained = True
            
            # Calculate training metrics
            predictions = self.model.predict(X_scaled)
            mse = np.mean((predictions - y) ** 2)
            
            return {
                'success': True,
                'training_samples': len(self.training_data),
                'mse': mse,
                'feature_importance': self._get_feature_importance()
            }
            
        except Exception as e:
            logger.error(f"Model training failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance from the trained model."""
        if not self.is_trained:
            return {}
        
        try:
            if hasattr(self.model, 'feature_importances_'):
                importances = self.model.feature_importances_
            elif hasattr(self.model, 'get_booster'):
                importances = self.model.get_booster().get_score(importance_type='gain')
                # Convert to array and align with feature names
                importances = [float(importances.get(f'f{i}', 0)) for i in range(len(self.feature_names))]
            else:
                return {}
            
            return dict(zip(self.feature_names, importances))
            
        except Exception as e:
            logger.error(f"Feature importance extraction failed: {e}")
            return {}


class DeterminantalPointProcesses:
    """
    Advanced diversification using determinantal point processes (DPP).
    
    DPP provides a principled approach to result diversification by selecting
    diverse subsets based on kernel similarity matrices.
    """
    
    def __init__(self, lambda_param: float = 0.7):
        """
        Initialize DPP diversification.
        
        Args:
            lambda_param: Trade-off between relevance and diversity (0-1)
        """
        self.lambda_param = lambda_param
    
    def compute_similarity_kernel(self, documents: List[Dict]) -> np.ndarray:
        """
        Compute similarity kernel matrix for documents.
        
        Args:
            documents: List of documents with vectors
            
        Returns:
            Similarity kernel matrix
        """
        n = len(documents)
        kernel = np.zeros((n, n))
        
        for i in range(n):
            for j in range(n):
                if i == j:
                    kernel[i, j] = 1.0
                else:
                    # Cosine similarity between document vectors
                    vec_i = documents[i].get('vector', [])
                    vec_j = documents[j].get('vector', [])
                    
                    if vec_i and vec_j and len(vec_i) == len(vec_j):
                        similarity = cosine_similarity([vec_i], [vec_j])[0][0]
                        kernel[i, j] = max(0, similarity)  # Ensure non-negative
        
        return kernel
    
    def diversify_results(self, results: List[Dict], top_k: int = 10) -> List[Dict]:
        """
        Diversify search results using DPP.
        
        Args:
            results: Initial search results
            top_k: Number of diverse results to return
            
        Returns:
            Diversified results
        """
        if len(results) <= top_k:
            return results
        
        try:
            # Extract documents and scores
            documents = [r.get('document', r) for r in results]
            scores = np.array([r.get('score', 0.0) for r in results])
            
            # Normalize scores
            if np.max(scores) > 0:
                scores = scores / np.max(scores)
            
            # Compute similarity kernel
            kernel = self.compute_similarity_kernel(documents)
            
            # Create quality matrix (diagonal matrix with scores)
            quality = np.diag(scores ** 2)
            
            # Create DPP kernel: L = (1-λ) * quality + λ * similarity
            dpp_kernel = (1 - self.lambda_param) * quality + self.lambda_param * kernel
            
            # Greedy DPP sampling
            selected_indices = self._greedy_dpp_sampling(dpp_kernel, top_k)
            
            # Return selected results
            diversified_results = [results[i] for i in selected_indices]
            
            # Mark as diversified
            for result in diversified_results:
                result['diversification_method'] = 'dpp'
            
            return diversified_results
            
        except Exception as e:
            logger.error(f"DPP diversification failed: {e}")
            # Fallback to MMR
            return self._mmr_fallback(results, top_k)
    
    def _greedy_dpp_sampling(self, kernel: np.ndarray, k: int) -> List[int]:
        """
        Greedy sampling for DPP.
        
        Args:
            kernel: DPP kernel matrix
            k: Number of items to select
            
        Returns:
            Indices of selected items
        """
        n = kernel.shape[0]
        selected = []
        remaining = set(range(n))
        
        for _ in range(min(k, n)):
            best_idx = -1
            best_gain = -np.inf
            
            for idx in remaining:
                # Calculate marginal gain
                if not selected:
                    gain = kernel[idx, idx]
                else:
                    # Compute determinant ratio
                    selected_indices = selected + [idx]
                    submatrix = kernel[np.ix_(selected_indices, selected_indices)]
                    gain = np.linalg.det(submatrix)
                
                if gain > best_gain:
                    best_gain = gain
                    best_idx = idx
            
            if best_idx >= 0:
                selected.append(best_idx)
                remaining.remove(best_idx)
        
        return selected
    
    def _mmr_fallback(self, results: List[Dict], top_k: int) -> List[Dict]:
        """
        Fallback to Maximal Marginal Relevance if DPP fails.
        
        Args:
            results: Search results
            top_k: Number of results to return
            
        Returns:
            Diversified results using MMR
        """
        selected = []
        remaining = results.copy()
        
        # Select highest scoring result first
        if remaining:
            selected.append(remaining.pop(0))
        
        while len(selected) < top_k and remaining:
            best_idx = 0
            best_mmr = -np.inf
            
            for i, candidate in enumerate(remaining):
                relevance = candidate.get('score', 0.0)
                
                # Calculate maximum similarity to selected
                max_similarity = 0.0
                for sel in selected:
                    sim = self._compute_similarity(candidate, sel)
                    max_similarity = max(max_similarity, sim)
                
                # MMR score
                mmr_score = self.lambda_param * relevance - (1 - self.lambda_param) * max_similarity
                
                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_idx = i
            
            selected.append(remaining.pop(best_idx))
        
        for result in selected:
            result['diversification_method'] = 'mmr_fallback'
        
        return selected
    
    def _compute_similarity(self, doc1: Dict, doc2: Dict) -> float:
        """Compute cosine similarity between two documents."""
        vec1 = doc1.get('vector', doc1.get('document', {}).get('vector', []))
        vec2 = doc2.get('vector', doc2.get('document', {}).get('vector', []))
        
        if vec1 and vec2 and len(vec1) == len(vec2):
            return cosine_similarity([vec1], [vec2])[0][0]
        return 0.0


class LocalSemanticSearch:
    """
    Semantic search using local embedding models.
    
    When API-based embeddings are unavailable or too slow, local models
    provide a fallback for semantic search capabilities.
    """
    
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        """
        Initialize local semantic search.
        
        Args:
            model_name: Name of the sentence-transformers model to use
        """
        self.model_name = model_name
        self.model = None
        self.index = None
        self.documents = []
        
        # Initialize model
        self._load_model()
    
    def _load_model(self):
        """Load the local embedding model."""
        try:
            logger.info(f"Loading local embedding model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            logger.info("Local embedding model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load local embedding model: {e}")
            self.model = None
    
    def embed_documents(self, documents: List[Dict]) -> List[np.ndarray]:
        """
        Generate embeddings for documents using local model.
        
        Args:
            documents: List of documents with text content
            
        Returns:
            List of embedding vectors
        """
        if not self.model:
            logger.warning("Local model not available, cannot generate embeddings")
            return []
        
        try:
            texts = [doc.get('text', doc.get('sentence', '')) for doc in documents]
            embeddings = self.model.encode(texts, show_progress_bar=False)
            return embeddings.tolist()
            
        except Exception as e:
            logger.error(f"Document embedding failed: {e}")
            return []
    
    def embed_query(self, query: str) -> np.ndarray:
        """
        Generate embedding for search query.
        
        Args:
            query: Search query string
            
        Returns:
            Query embedding vector
        """
        if not self.model:
            logger.warning("Local model not available, cannot generate query embedding")
            return np.array([])
        
        try:
            embedding = self.model.encode(query, show_progress_bar=False)
            return embedding
            
        except Exception as e:
            logger.error(f"Query embedding failed: {e}")
            return np.array([])
    
    def build_faiss_index(self, embeddings: List[np.ndarray]):
        """
        Build FAISS index for fast similarity search.
        
        Args:
            embeddings: List of embedding vectors
        """
        if not embeddings:
            return
        
        try:
            embedding_array = np.array(embeddings).astype('float32')
            dimension = embedding_array.shape[1]
            
            # Create FAISS index
            self.index = faiss.IndexFlatL2(dimension)
            self.index.add(embedding_array)
            
            logger.info(f"FAISS index built with {len(embeddings)} documents")
            
        except Exception as e:
            logger.error(f"FAISS index building failed: {e}")
            self.index = None
    
    def search(self, query_embedding: np.ndarray, top_k: int = 10) -> List[Tuple[int, float]]:
        """
        Search using FAISS index.
        
        Args:
            query_embedding: Query embedding vector
            top_k: Number of results to return
            
        Returns:
            List of (index, distance) tuples
        """
        if not self.index or len(query_embedding) == 0:
            return []
        
        try:
            query_embedding = query_embedding.reshape(1, -1).astype('float32')
            distances, indices = self.index.search(query_embedding, top_k)
            
            results = list(zip(indices[0], distances[0]))
            return results
            
        except Exception as e:
            logger.error(f"FAISS search failed: {e}")
            return []
    
    def semantic_search(self, query: str, documents: List[Dict], top_k: int = 10) -> List[Dict]:
        """
        Perform semantic search using local embeddings.
        
        Args:
            query: Search query
            documents: Documents to search
            top_k: Number of results to return
            
        Returns:
            Ranked search results with semantic scores
        """
        if not self.model or not documents:
            return []
        
        try:
            # Generate query embedding
            query_embedding = self.embed_query(query)
            if len(query_embedding) == 0:
                return []
            
            # Generate document embeddings
            doc_embeddings = self.embed_documents(documents)
            if not doc_embeddings:
                return []
            
            # Build FAISS index
            self.build_faiss_index(doc_embeddings)
            
            # Search
            search_results = self.search(query_embedding, top_k)
            
            # Format results
            results = []
            for idx, distance in search_results:
                if idx < len(documents):
                    doc = documents[idx].copy()
                    # Convert distance to similarity score
                    similarity = 1.0 / (1.0 + distance)
                    doc['semantic_score'] = similarity
                    doc['search_method'] = 'local_semantic'
                    results.append(doc)
            
            return results
            
        except Exception as e:
            logger.error(f"Local semantic search failed: {e}")
            return []


class FacetedSearch:
    """
    Faceted search with advanced filtering capabilities.
    
    Enables users to filter search results by various facets like
    file type, date range, metadata, etc.
    """
    
    def __init__(self):
        """Initialize faceted search."""
        self.available_facets = {}
        self.facet_counts = defaultdict(lambda: defaultdict(int))
    
    def extract_facets(self, documents: List[Dict]) -> Dict[str, Dict[str, int]]:
        """
        Extract available facets and their counts from documents.
        
        Args:
            documents: List of documents to analyze
            
        Returns:
            Dictionary of facets with their value counts
        """
        facets = defaultdict(lambda: defaultdict(int))
        
        for doc in documents:
            metadata = doc.get('metadata', {})
            
            # File type facet
            file_type = metadata.get('file_type', 'unknown')
            facets['file_type'][file_type] += 1
            
            # File name facet (first part)
            file_name = doc.get('file_name', '')
            if file_name:
                name_parts = file_name.split('-')[0]
                facets['file_name'][name_parts] += 1
            
            # Date facet (if available)
            if 'date' in metadata:
                date_str = metadata['date']
                try:
                    date_obj = datetime.fromisoformat(date_str)
                    date_facet = date_obj.strftime('%Y-%m')
                    facets['date'][date_facet] += 1
                except:
                    pass
            
            # Custom metadata facets
            for key, value in metadata.items():
                if key not in ['file_type', 'date']:
                    if isinstance(value, str):
                        facets[f'meta_{key}'][value] += 1
        
        self.available_facets = dict(facets)
        return dict(facets)
    
    def apply_filters(self, documents: List[Dict], filters: Dict[str, Any]) -> List[Dict]:
        """
        Apply faceted filters to documents.
        
        Args:
            documents: Documents to filter
            filters: Dictionary of facet filters
            
        Returns:
            Filtered documents
        """
        filtered = documents.copy()
        
        for facet, values in filters.items():
            if not values:
                continue
            
            # Handle both single values and lists
            if not isinstance(values, list):
                values = [values]
            
            # Apply filter based on facet type
            if facet == 'file_type':
                filtered = [doc for doc in filtered 
                          if doc.get('metadata', {}).get('file_type') in values]
            
            elif facet == 'file_name':
                filtered = [doc for doc in filtered 
                          if any(val in doc.get('file_name', '') for val in values)]
            
            elif facet == 'date':
                filtered = [doc for doc in filtered 
                          if self._date_filter(doc, values)]
            
            elif facet.startswith('meta_'):
                meta_key = facet[5:]  # Remove 'meta_' prefix
                filtered = [doc for doc in filtered 
                          if doc.get('metadata', {}).get(meta_key) in values]
        
        return filtered
    
    def _date_filter(self, document: Dict, date_ranges: List[str]) -> bool:
        """
        Filter document by date ranges.
        
        Args:
            document: Document to check
            date_ranges: List of date range strings (e.g., '2024-01', '2024-02')
            
        Returns:
            True if document matches any date range
        """
        metadata = document.get('metadata', {})
        date_str = metadata.get('date', '')
        
        if not date_str:
            return False
        
        try:
            date_obj = datetime.fromisoformat(date_str)
            doc_month = date_obj.strftime('%Y-%m')
            return doc_month in date_ranges
        except:
            return False
    
    def get_filter_suggestions(self, query: str, documents: List[Dict]) -> Dict[str, List[str]]:
        """
        Suggest relevant filters based on query and documents.
        
        Args:
            query: Search query
            documents: Documents to analyze
            
        Returns:
            Dictionary of suggested filter values per facet
        """
        suggestions = {}
        
        # Extract facets
        facets = self.extract_facets(documents)
        
        # Analyze query for filter hints
        query_lower = query.lower()
        
        # Suggest file types based on query terms
        if 'vm' in query_lower or 'virtual' in query_lower:
            suggestions['file_type'] = ['.py', '.go']  # Code files
        elif 'doc' in query_lower or 'guide' in query_lower:
            suggestions['file_type'] = ['.md']  # Documentation
        
        # Add top facets by count
        for facet, values in facets.items():
            if facet not in suggestions:
                top_values = sorted(values.items(), key=lambda x: x[1], reverse=True)[:5]
                suggestions[facet] = [v[0] for v in top_values]
        
        return suggestions


class QueryOptimizer:
    """
    Query-time optimization for performance improvement.
    
    Optimizes queries through caching, rewriting, and parallel processing.
    """
    
    def __init__(self):
        """Initialize query optimizer."""
        self.query_cache = {}
        self.query_stats = defaultdict(lambda: {'count': 0, 'total_time': 0.0})
        self.rewrite_rules = self._init_rewrite_rules()
    
    def _init_rewrite_rules(self) -> List[Dict]:
        """Initialize query rewrite rules."""
        return [
            {
                'pattern': r'how to (\w+)',
                'replacement': r'\1 tutorial guide',
                'description': 'Expand "how to" queries'
            },
            {
                'pattern': r'what is (\w+)',
                'replacement': r'\1 definition explanation',
                'description': 'Expand "what is" queries'
            },
            {
                'pattern': r'(\w+) costs?',
                'replacement': r'\1 pricing cost optimization',
                'description': 'Expand cost-related queries'
            }
        ]
    
    def optimize_query(self, query: str) -> Dict[str, Any]:
        """
        Optimize a search query.
        
        Args:
            query: Original search query
            
        Returns:
            Dictionary with optimized query and metadata
        """
        start_time = time.time()
        
        # Check cache
        cache_key = hashlib.md5(query.encode()).hexdigest()
        if cache_key in self.query_cache:
            cached = self.query_cache[cache_key]
            cached['cache_hit'] = True
            return cached
        
        # Apply rewrite rules
        optimized_query = self._apply_rewrite_rules(query)
        
        # Extract query terms
        query_terms = self._extract_terms(optimized_query)
        
        # Generate query variations
        variations = self._generate_variations(query_terms)
        
        result = {
            'original_query': query,
            'optimized_query': optimized_query,
            'query_terms': query_terms,
            'variations': variations,
            'cache_hit': False,
            'optimization_time': time.time() - start_time
        }
        
        # Cache result
        self.query_cache[cache_key] = result
        
        # Update stats
        self.query_stats[query]['count'] += 1
        self.query_stats[query]['total_time'] += result['optimization_time']
        
        return result
    
    def _apply_rewrite_rules(self, query: str) -> str:
        """Apply query rewrite rules."""
        import re
        optimized = query
        
        for rule in self.rewrite_rules:
            pattern = rule['pattern']
            replacement = rule['replacement']
            optimized = re.sub(pattern, replacement, optimized, flags=re.IGNORECASE)
        
        return optimized
    
    def _extract_terms(self, query: str) -> List[str]:
        """Extract significant terms from query."""
        # Simple tokenization and stopword removal
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        terms = query.lower().split()
        significant_terms = [t for t in terms if t not in stopwords and len(t) > 2]
        return significant_terms
    
    def _generate_variations(self, terms: List[str]) -> List[str]:
        """Generate query variations for better recall."""
        variations = []
        
        # Original query
        variations.append(' '.join(terms))
        
        # Pairwise combinations
        if len(terms) >= 2:
            for i in range(len(terms) - 1):
                variations.append(f"{terms[i]} {terms[i+1]}")
        
        # Single terms (for broad search)
        variations.extend(terms)
        
        return list(set(variations))  # Remove duplicates
    
    def get_query_stats(self) -> Dict[str, Any]:
        """Get query optimization statistics."""
        stats = dict(self.query_stats)
        
        # Calculate averages
        for query, data in stats.items():
            if data['count'] > 0:
                data['avg_time'] = data['total_time'] / data['count']
        
        return {
            'total_queries': len(stats),
            'cache_size': len(self.query_cache),
            'query_stats': stats
        }


class ResultCache:
    """
    Result caching for common queries to improve performance.
    
    Caches search results to avoid redundant processing.
    """
    
    def __init__(self, redis_client=None, ttl: int = 3600):
        """
        Initialize result cache.
        
        Args:
            redis_client: Optional Redis client for distributed caching
            ttl: Time-to-live for cache entries in seconds
        """
        self.redis_client = redis_client
        self.ttl = ttl
        self.local_cache = {}
        self.cache_stats = defaultdict(lambda: {'hits': 0, 'misses': 0})
    
    def generate_cache_key(self, query: str, filters: Dict = None, top_k: int = 10) -> str:
        """
        Generate cache key for search parameters.
        
        Args:
            query: Search query
            filters: Search filters
            top_k: Number of results
            
        Returns:
            Cache key string
        """
        key_data = {
            'query': query,
            'filters': sorted(filters.items()) if filters else [],
            'top_k': top_k
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return f"search_result:{hashlib.md5(key_str.encode()).hexdigest()}"
    
    def get(self, query: str, filters: Dict = None, top_k: int = 10) -> Optional[List[Dict]]:
        """
        Get cached results if available.
        
        Args:
            query: Search query
            filters: Search filters
            top_k: Number of results
            
        Returns:
            Cached results or None
        """
        cache_key = self.generate_cache_key(query, filters, top_k)
        
        # Try Redis first
        if self.redis_client:
            try:
                cached_data = self.redis_client.get(cache_key)
                if cached_data:
                    results = json.loads(cached_data)
                    self.cache_stats[cache_key]['hits'] += 1
                    return results
            except Exception as e:
                logger.warning(f"Redis cache get failed: {e}")
        
        # Fall back to local cache
        if cache_key in self.local_cache:
            self.cache_stats[cache_key]['hits'] += 1
            return self.local_cache[cache_key]
        
        self.cache_stats[cache_key]['misses'] += 1
        return None
    
    def set(self, query: str, results: List[Dict], filters: Dict = None, top_k: int = 10):
        """
        Cache search results.
        
        Args:
            query: Search query
            results: Search results to cache
            filters: Search filters
            top_k: Number of results
        """
        cache_key = self.generate_cache_key(query, filters, top_k)
        
        # Store in Redis
        if self.redis_client:
            try:
                self.redis_client.setex(cache_key, self.ttl, json.dumps(results))
            except Exception as e:
                logger.warning(f"Redis cache set failed: {e}")
        
        # Store in local cache
        self.local_cache[cache_key] = results
    
    def invalidate(self, query: str = None, filters: Dict = None):
        """
        Invalidate cache entries.
        
        Args:
            query: Specific query to invalidate (None for all)
            filters: Specific filters to invalidate
        """
        if query:
            cache_key = self.generate_cache_key(query, filters)
            if cache_key in self.local_cache:
                del self.local_cache[cache_key]
            if self.redis_client:
                try:
                    self.redis_client.delete(cache_key)
                except Exception as e:
                    logger.warning(f"Redis cache invalidation failed: {e}")
        else:
            # Clear all cache
            self.local_cache.clear()
            if self.redis_client:
                try:
                    # Note: This would clear all keys with pattern in production
                    pass
                except Exception as e:
                    logger.warning(f"Redis cache clear failed: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_hits = sum(stats['hits'] for stats in self.cache_stats.values())
        total_misses = sum(stats['misses'] for stats in self.cache_stats.values())
        total_requests = total_hits + total_misses
        
        hit_rate = total_hits / total_requests if total_requests > 0 else 0.0
        
        return {
            'local_cache_size': len(self.local_cache),
            'total_hits': total_hits,
            'total_misses': total_misses,
            'hit_rate': hit_rate,
            'tracked_keys': len(self.cache_stats)
        }


class ABTestFramework:
    """
    A/B testing framework for ranking algorithms.
    
    Enables comparison of different ranking strategies to determine
    the most effective approach.
    """
    
    def __init__(self):
        """Initialize A/B testing framework."""
        self.experiments = {}
        self.experiment_results = defaultdict(list)
    
    def create_experiment(self, experiment_id: str, variants: List[Dict], 
                         traffic_split: Dict[str, float] = None) -> Dict[str, Any]:
        """
        Create a new A/B test experiment.
        
        Args:
            experiment_id: Unique identifier for the experiment
            variants: List of variant configurations
            traffic_split: Traffic split per variant (default: equal split)
            
        Returns:
            Experiment configuration
        """
        if traffic_split is None:
            # Equal split
            split = 1.0 / len(variants)
            traffic_split = {v['id']: split for v in variants}
        
        experiment = {
            'id': experiment_id,
            'variants': variants,
            'traffic_split': traffic_split,
            'created_at': datetime.now().isoformat(),
            'status': 'active'
        }
        
        self.experiments[experiment_id] = experiment
        return experiment
    
    def assign_variant(self, experiment_id: str, user_id: str = None) -> str:
        """
        Assign a user to a variant for testing.
        
        Args:
            experiment_id: Experiment identifier
            user_id: User identifier for consistent assignment
            
        Returns:
            Assigned variant ID
        """
        if experiment_id not in self.experiments:
            return 'default'
        
        experiment = self.experiments[experiment_id]
        
        # Consistent assignment based on user ID
        if user_id:
            user_hash = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
            variants = list(experiment['traffic_split'].keys())
            variant_index = user_hash % len(variants)
            return variants[variant_index]
        
        # Random assignment
        rand = random.random()
        cumulative = 0.0
        for variant_id, split in experiment['traffic_split'].items():
            cumulative += split
            if rand <= cumulative:
                return variant_id
        
        return list(experiment['traffic_split'].keys())[0]
    
    def record_metric(self, experiment_id: str, variant_id: str, 
                     metric_name: str, metric_value: float):
        """
        Record a metric for a variant.
        
        Args:
            experiment_id: Experiment identifier
            variant_id: Variant identifier
            metric_name: Name of the metric (e.g., 'ctr', 'dwell_time')
            metric_value: Value of the metric
        """
        result = {
            'experiment_id': experiment_id,
            'variant_id': variant_id,
            'metric_name': metric_name,
            'metric_value': metric_value,
            'timestamp': datetime.now().isoformat()
        }
        
        self.experiment_results[(experiment_id, variant_id)].append(result)
    
    def analyze_results(self, experiment_id: str) -> Dict[str, Any]:
        """
        Analyze A/B test results.
        
        Args:
            experiment_id: Experiment identifier
            
        Returns:
            Analysis results with statistical significance
        """
        if experiment_id not in self.experiments:
            return {'error': 'Experiment not found'}
        
        experiment = self.experiments[experiment_id]
        analysis = {}
        
        for variant in experiment['variants']:
            variant_id = variant['id']
            results = self.experiment_results[(experiment_id, variant_id)]
            
            if not results:
                analysis[variant_id] = {'error': 'No data'}
                continue
            
            # Calculate metrics by type
            metrics = defaultdict(list)
            for result in results:
                metrics[result['metric_name']].append(result['metric_value'])
            
            variant_analysis = {}
            for metric_name, values in metrics.items():
                variant_analysis[metric_name] = {
                    'mean': np.mean(values),
                    'std': np.std(values),
                    'count': len(values),
                    'min': np.min(values),
                    'max': np.max(values)
                }
            
            analysis[variant_id] = variant_analysis
        
        # Calculate statistical significance (simplified)
        # In production, use proper statistical tests
        analysis['statistical_significance'] = self._calculate_significance(analysis)
        
        return analysis
    
    def _calculate_significance(self, analysis: Dict) -> Dict[str, Any]:
        """Calculate statistical significance between variants."""
        # Simplified significance calculation
        # In production, use t-tests, ANOVA, etc.
        return {
            'note': 'Statistical significance calculation not implemented',
            'recommendation': 'Use proper statistical tests in production'
        }
    
    def get_experiment_config(self, experiment_id: str) -> Dict[str, Any]:
        """Get experiment configuration."""
        return self.experiments.get(experiment_id, {})


class PersonalizationEngine:
    """
    Personalization based on user behavior and preferences.
    
    Adapts search results based on user history, preferences, and behavior patterns.
    """
    
    def __init__(self):
        """Initialize personalization engine."""
        self.user_profiles = {}
        self.user_history = defaultdict(list)
        self.global_preferences = defaultdict(int)
    
    def record_user_action(self, user_id: str, action: str, 
                         document_id: str, context: Dict = None):
        """
        Record a user action for personalization.
        
        Args:
            user_id: User identifier
            action: Action type (click, dwell, bookmark, share)
            document_id: Document identifier
            context: Additional context (query, timestamp, etc.)
        """
        action_record = {
            'action': action,
            'document_id': document_id,
            'context': context or {},
            'timestamp': datetime.now().isoformat()
        }
        
        self.user_history[user_id].append(action_record)
        
        # Update user profile
        self._update_user_profile(user_id, action_record)
    
    def _update_user_profile(self, user_id: str, action_record: Dict):
        """Update user profile based on action."""
        if user_id not in self.user_profiles:
            self.user_profiles[user_id] = {
                'preferences': defaultdict(int),
                'document_types': defaultdict(int),
                'query_patterns': defaultdict(int)
            }
        
        profile = self.user_profiles[user_id]
        
        # Update preferences based on action
        action = action_record['action']
        if action == 'click':
            profile['preferences']['relevance_weight'] += 0.1
        elif action == 'dwell':
            profile['preferences']['depth_weight'] += 0.1
        elif action == 'bookmark':
            profile['preferences']['bookmark_weight'] += 0.2
        
        # Update document type preferences
        context = action_record.get('context', {})
        doc_type = context.get('document_type', 'unknown')
        profile['document_types'][doc_type] += 1
        
        # Update query patterns
        query = context.get('query', '')
        if query:
            terms = query.lower().split()
            for term in terms:
                profile['query_patterns'][term] += 1
    
    def get_personalized_ranking(self, user_id: str, results: List[Dict]) -> List[Dict]:
        """
        Re-rank results based on user personalization.
        
        Args:
            user_id: User identifier
            results: Initial search results
            
        Returns:
            Personalized re-ranked results
        """
        if user_id not in self.user_profiles:
            return results
        
        profile = self.user_profiles[user_id]
        
        # Calculate personalized scores
        for result in results:
            personalized_score = result.get('score', 0.0)
            
            # Apply preference weights
            pref = profile['preferences']
            personalized_score *= (1.0 + pref.get('relevance_weight', 0.0))
            
            # Apply document type preferences
            doc_type = result.get('document', {}).get('metadata', {}).get('file_type', 'unknown')
            type_count = profile['document_types'].get(doc_type, 0)
            if type_count > 0:
                personalized_score *= (1.0 + min(type_count * 0.1, 0.5))  # Cap at 50% boost
            
            result['personalized_score'] = personalized_score
            result['personalization_applied'] = True
        
        # Sort by personalized scores
        ranked = sorted(results, key=lambda x: x.get('personalized_score', 0), reverse=True)
        
        return ranked
    
    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """Get user profile for analysis."""
        if user_id not in self.user_profiles:
            return {'error': 'User not found'}
        
        profile = self.user_profiles[user_id]
        
        return {
            'user_id': user_id,
            'preferences': dict(profile['preferences']),
            'document_types': dict(profile['document_types']),
            'query_patterns': dict(profile['query_patterns']),
            'total_actions': len(self.user_history[user_id])
        }
    
    def get_recommendations(self, user_id: str, n: int = 5) -> List[Dict]:
        """
        Get personalized recommendations for a user.
        
        Args:
            user_id: User identifier
            n: Number of recommendations
            
        Returns:
            List of recommended document types or queries
        """
        if user_id not in self.user_profiles:
            return []
        
        profile = self.user_profiles[user_id]
        
        # Recommend based on document type preferences
        type_recommendations = sorted(
            profile['document_types'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:n]
        
        # Recommend based on query patterns
        query_recommendations = sorted(
            profile['query_patterns'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:n]
        
        return [
            {
                'type': 'document_type',
                'recommendations': [t[0] for t in type_recommendations]
            },
            {
                'type': 'query',
                'recommendations': [q[0] for q in query_recommendations]
            }
        ]


class EnhancedRAGEngine:
    """
    Enhanced RAG engine combining all advanced features.
    
    Integrates learnable ranking, diversification, semantic search,
    faceted search, query optimization, caching, A/B testing, and personalization.
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize enhanced RAG engine.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        
        # Initialize components
        self.learnable_ranking = LearnableRanking(
            model_type=self.config.get('ranking_model', 'xgboost')
        )
        self.dpp = DeterminantalPointProcesses(
            lambda_param=self.config.get('dpp_lambda', 0.7)
        )
        self.local_semantic = LocalSemanticSearch(
            model_name=self.config.get('local_model', 'all-MiniLM-L6-v2')
        )
        self.faceted_search = FacetedSearch()
        self.query_optimizer = QueryOptimizer()
        
        # Initialize Redis for caching
        redis_client = None
        try:
            redis_url = self.config.get('redis_url', os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
            redis_client = redis.from_url(redis_url, decode_responses=True)
            redis_client.ping()
        except:
            logger.warning("Redis not available, using local cache only")
        
        self.result_cache = ResultCache(
            redis_client=redis_client,
            ttl=self.config.get('cache_ttl', 3600)
        )
        
        self.ab_test = ABTestFramework()
        self.personalization = PersonalizationEngine()
        
        logger.info("Enhanced RAG engine initialized")
    
    def search(self, query: str, user_id: str = None, filters: Dict = None,
               top_k: int = 10, enable_features: Dict = None) -> Dict[str, Any]:
        """
        Perform enhanced search with all features.
        
        Args:
            query: Search query
            user_id: User identifier for personalization
            filters: Faceted filters
            top_k: Number of results
            enable_features: Dictionary to enable/disable specific features
            
        Returns:
            Enhanced search results
        """
        enable_features = enable_features or {}
        
        start_time = time.time()
        
        # Check cache
        cached_results = self.result_cache.get(query, filters, top_k)
        if cached_results and enable_features.get('cache', True):
            return {
                'results': cached_results,
                'cache_hit': True,
                'processing_time': time.time() - start_time
            }
        
        # Optimize query
        if enable_features.get('query_optimization', True):
            optimized = self.query_optimizer.optimize_query(query)
            search_query = optimized['optimized_query']
        else:
            search_query = query
        
        # Get initial results (would call base RAG engine here)
        # For now, return empty results as this is a framework
        results = []
        
        # Apply faceted filters
        if filters and enable_features.get('faceted_search', True):
            results = self.faceted_search.apply_filters(results, filters)
        
        # Apply learnable ranking
        if enable_features.get('learnable_ranking', True):
            results = self.learnable_ranking.rank_results(search_query, results)
        
        # Apply diversification
        if enable_features.get('diversification', True):
            results = self.dpp.diversify_results(results, top_k)
        
        # Apply personalization
        if user_id and enable_features.get('personalization', True):
            results = self.personalization.get_personalized_ranking(user_id, results)
        
        # Cache results
        if enable_features.get('cache', True):
            self.result_cache.set(query, results, filters, top_k)
        
        return {
            'results': results,
            'cache_hit': False,
            'processing_time': time.time() - start_time,
            'query_optimization': optimized if enable_features.get('query_optimization', True) else None,
            'features_applied': enable_features
        }
    
    def add_feedback(self, query: str, document: Dict, relevance_score: float,
                    user_id: str = None, **kwargs):
        """Add feedback for learnable ranking and personalization."""
        # Update learnable ranking
        self.learnable_ranking.add_feedback(query, document, relevance_score, **kwargs)
        
        # Update personalization
        if user_id:
            self.personalization.record_user_action(
                user_id, 'feedback', document.get('id', ''),
                {'query': query, 'relevance': relevance_score}
            )
    
    def train_ranking_model(self) -> Dict[str, Any]:
        """Train the learnable ranking model."""
        return self.learnable_ranking.train_model()
    
    def get_analytics(self) -> Dict[str, Any]:
        """Get analytics across all components."""
        return {
            'cache_stats': self.result_cache.get_stats(),
            'query_stats': self.query_optimizer.get_query_stats(),
            'ab_test_results': {k: self.ab_test.analyze_results(k) 
                              for k in self.ab_test.experiments.keys()}
        }