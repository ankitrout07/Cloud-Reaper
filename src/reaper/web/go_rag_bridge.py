"""
Go RAG Bridge Client
Provides async interface to the Go RAG search HTTP server
"""

import asyncio
import os
from typing import Any, Dict, List, Optional

from reaper.web.go_bridge_base import (
    BaseGoBridge,
    GoBridgeConfig,
    GoBridgeConnectionError,
    GoBridgeTimeoutError,
    create_bridge_client
)


class RAGBridge(BaseGoBridge):
    """
    Async client for Go RAG search engine.
    Provides high-performance vector and hybrid search capabilities.
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 7074,
        timeout: float = 30.0,
        enabled: bool = True
    ):
        """
        Initialize RAG bridge client.
        
        Args:
            host: Go RAG server host
            port: Go RAG server port (default 7074)
            timeout: HTTP request timeout in seconds
            enabled: Whether the bridge is enabled
        """
        super().__init__(host, port, timeout, enabled)
    
    async def index_documents(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Index documents in the Go RAG engine.
        
        Args:
            documents: List of document dictionaries with text, vectors, and metadata
            
        Returns:
            Indexing result with document counts
        """
        return await self._make_request(
            "POST",
            "/api/rag/index",
            json_data={"documents": documents}
        )
    
    async def search(
        self,
        query: str,
        query_vector: Optional[List[float]] = None,
        top_k: int = 10,
        file_filter: Optional[str] = None,
        file_type_filter: Optional[str] = None,
        lambda_param: float = 0.6,
        rrf_constant: int = 60,
        enable_bm25: bool = True,
        enable_dense: bool = True,
        enable_mmr: bool = False
    ) -> Dict[str, Any]:
        """
        Perform hybrid search in the Go RAG engine.
        
        Args:
            query: Search query text
            query_vector: Optional pre-computed query vector
            top_k: Number of results to return
            file_filter: Optional filename filter
            file_type_filter: Optional file type filter
            lambda_param: MMR lambda parameter (0-1)
            rrf_constant: RRF constant for rank fusion
            enable_bm25: Enable BM25 sparse search
            enable_dense: Enable dense vector search
            enable_mmr: Enable MMR diversification
            
        Returns:
            Search results with documents and scores
        """
        return await self._make_request(
            "POST",
            "/api/rag/search",
            json_data={
                "query": query,
                "query_vector": query_vector,
                "top_k": top_k,
                "file_filter": file_filter,
                "file_type_filter": file_type_filter,
                "lambda_param": lambda_param,
                "rrf_constant": rrf_constant,
                "enable_bm25": enable_bm25,
                "enable_dense": enable_dense,
                "enable_mmr": enable_mmr
            }
        )
    
    async def dense_search(
        self,
        query_vector: List[float],
        top_k: int = 10
    ) -> Dict[str, Any]:
        """
        Perform dense vector search only.
        
        Args:
            query_vector: Query vector
            top_k: Number of results to return
            
        Returns:
            Dense search results
        """
        return await self._make_request(
            "POST",
            "/api/rag/dense",
            json_data={
                "query_vector": query_vector,
                "top_k": top_k
            }
        )
    
    async def sparse_search(
        self,
        query: str,
        top_k: int = 10
    ) -> Dict[str, Any]:
        """
        Perform BM25 sparse search only.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            
        Returns:
            Sparse search results
        """
        return await self._make_request(
            "POST",
            "/api/rag/sparse",
            json_data={
                "query": query,
                "top_k": top_k
            }
        )
    
    async def clear_index(self) -> Dict[str, Any]:
        """
        Clear all indexed documents.
        
        Returns:
            Clear operation result
        """
        return await self._make_request("POST", "/api/rag/clear")
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get RAG engine statistics.
        
        Returns:
            Engine statistics including document counts and index info
        """
        return await self._make_request("GET", "/api/rag/stats")
    
    async def expand_query(self, query: str) -> Dict[str, Any]:
        """
        Expand query with domain-specific synonyms.
        
        Args:
            query: Original query
            
        Returns:
            Expanded query variants
        """
        return await self._make_request(
            "POST",
            "/api/rag/expand",
            json_data={"query": query}
        )


def create_rag_bridge(**kwargs) -> RAGBridge:
    """
    Factory function to create RAG bridge with standardized configuration.
    
    Args:
        **kwargs: Additional constructor arguments
        
    Returns:
        Configured RAG bridge instance
    """
    return create_bridge_client(
        RAGBridge,
        "rag",
        **kwargs
    )


# Global singleton instance
_global_rag_bridge: Optional[RAGBridge] = None
_rag_bridge_lock = asyncio.Lock()


async def get_rag_bridge() -> RAGBridge:
    """
    Get or create the global RAG bridge instance.
    
    Returns:
        Global RAG bridge instance
    """
    global _global_rag_bridge
    
    async with _rag_bridge_lock:
        if _global_rag_bridge is None:
            _global_rag_bridge = create_rag_bridge()
        return _global_rag_bridge


async def close_rag_bridge():
    """Close the global RAG bridge instance."""
    global _global_rag_bridge
    
    async with _rag_bridge_lock:
        if _global_rag_bridge is not None:
            await _global_rag_bridge.close()
            _global_rag_bridge = None