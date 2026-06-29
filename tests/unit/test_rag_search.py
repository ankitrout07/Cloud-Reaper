# tests/unit/test_rag_search.py
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from reaper.rag import DocSearchEngine
from reaper.web.app_async import app


class TestDocSearchEngine(unittest.TestCase):
    @patch("google.genai.Client")
    @patch("pathlib.Path.rglob")
    @patch(
        "pathlib.Path.open",
        new_callable=unittest.mock.mock_open,
        read_data="## Section A\nThis is architecture.\n## Section B\nThis is deployment.",
    )
    def test_load_and_index_docs(self, _mock_file, mock_rglob, mock_client_class):
        # Setup mocks
        mock_rglob.return_value = [Path("docs/architecture.md")]

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.values = [0.1, 0.2, 0.3]
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response
        mock_client_class.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            engine = DocSearchEngine()
            engine.load_and_index_docs("docs")

            # Check that two chunks were split and embedded
            self.assertEqual(len(engine.docs_index), 2)
            self.assertEqual(engine.docs_index[0]["file_name"], "architecture.md")
            self.assertEqual(engine.docs_index[0]["vector"], [0.1, 0.2, 0.3])

    @patch("google.genai.Client")
    def test_query_docs(self, mock_client_class):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_embedding = MagicMock()
        # Mock query vector
        mock_embedding.values = [1.0, 0.0]
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response
        mock_client_class.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            engine = DocSearchEngine()
            # Directly populate index to avoid filesystem operations
            engine.docs_index = [
                {
                    "file_name": "architecture.md",
                    "text": "## Section A\nThis matches perfectly",
                    "vector": [1.0, 0.0],
                },
                {
                    "file_name": "deployment.md",
                    "text": "## Section B\nThis has zero similarity",
                    "vector": [0.0, 1.0],
                },
            ]

            results = engine.query_docs("perfect match", top_k=1)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["file"], "architecture.md")
            self.assertTrue(results[0]["confidence_score"].endswith("%"))

    @patch("google.genai.Client")
    def test_sentence_window_splitting(self, mock_client_class):
        """Verifies that multi-sentence sections are split and enriched with left/right context using semantic chunking."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.values = [0.1, 0.2]
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response
        mock_client_class.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            engine = DocSearchEngine()
            # Feed multi-sentence content with much more text to trigger multiple semantic chunks
            content = "# Title\nThis is sentence one. This is sentence two. This is sentence three. This is sentence four. This is sentence five. This is sentence six. This is sentence seven. This is sentence eight. This is sentence nine. This is sentence ten. This is sentence eleven. This is sentence twelve. This is sentence thirteen. This is sentence fourteen. This is sentence fifteen. This is sentence sixteen. This is sentence seventeen. This is sentence eighteen. This is sentence nineteen. This is sentence twenty."

            with (
                patch("pathlib.Path.open", unittest.mock.mock_open(read_data=content)),
                patch("pathlib.Path.rglob", return_value=[Path("docs/telemetry.md")]),
            ):
                engine.load_and_index_docs("docs")

            # With semantic chunking and sufficient content, we should get multiple chunks
            self.assertGreater(len(engine.docs_index), 1)

            # Verify that chunks have the expected structure
            for chunk in engine.docs_index:
                self.assertIn("sentence", chunk)
                self.assertIn("left_context", chunk)
                self.assertIn("right_context", chunk)
                self.assertIn("vector", chunk)

    @patch("google.genai.Client")
    def test_bm25_and_rrf(self, mock_client_class):
        """Verifies BM25 index creation and sparse-dense RRF fusion rankings."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_embedding = MagicMock()
        # Query vector close to document 2 but document 1 has perfect lexical match
        mock_embedding.values = [0.1, 0.9]
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response
        mock_client_class.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            engine = DocSearchEngine()
            engine.docs_index = [
                {
                    "file_name": "database.md",
                    "sentence": "Configure PostgreSQL replication targets.",
                    "vector": [0.9, 0.1],  # low dense similarity
                },
                {
                    "file_name": "other.md",
                    "sentence": "This is a random unrelated document.",
                    "vector": [0.1, 0.9],  # high dense similarity
                },
            ]

            # Searching for exact lexical keyword "PostgreSQL"
            results = engine.query_docs("PostgreSQL", top_k=2)

            # The PostgreSQL document should rank first due to strong sparse match and fusion
            self.assertEqual(results[0]["file"], "database.md")

    @patch("google.genai.Client")
    def test_cross_encoder_rerank_and_fallback(self, mock_client_class):
        """Verifies that the enhanced Cross-Encoder fallback works offline and ranks correctly."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.values = [0.5, 0.5]
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response
        mock_client_class.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            engine = DocSearchEngine()
            engine.docs_index = [
                {
                    "file_name": "a.md",
                    "sentence": "Q-Learning is a model-free reinforcement learning algorithm.",
                    "vector": [0.5, 0.5],
                },
                {
                    "file_name": "b.md",
                    "sentence": "Kubernetes runs containerized workloads in pods.",
                    "vector": [0.5, 0.5],
                },
            ]

            # Query has exact overlap with Q-Learning document
            results = engine.query_docs("Q-Learning", top_k=1)
            self.assertEqual(results[0]["file"], "a.md")
            # The enhanced algorithm should rank the correct document first
            # Just verify it returns a result with the expected structure
            self.assertIn("confidence_score", results[0])
            self.assertTrue(results[0]["confidence_score"].endswith("%"))

    @patch("google.genai.Client")
    def test_query_expansion(self, mock_client_class):
        """Verifies that query expansion generates relevant synonyms."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            engine = DocSearchEngine()

            # Test query expansion for domain terms
            expanded = engine._expand_query("optimize cost")
            self.assertIn("optimize cost", expanded)  # Original query
            # Should contain variations with synonyms
            self.assertTrue(
                any("price" in q or "expense" in q or "spending" in q for q in expanded)
            )
            self.assertTrue(
                any("improve" in q or "reduce" in q or "minimize" in q for q in expanded)
            )

    @patch("google.genai.Client")
    def test_metadata_filtering(self, mock_client_class):
        """Verifies that metadata filtering works correctly."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.values = [0.5, 0.5]
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response
        mock_client_class.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            engine = DocSearchEngine()
            engine.docs_index = [
                {
                    "file_name": "architecture.md",
                    "sentence": "System architecture details.",
                    "vector": [0.5, 0.5],
                    "metadata": {"file_type": ".md", "section": "architecture"},
                },
                {
                    "file_name": "setup.txt",
                    "sentence": "Setup instructions for the system.",
                    "vector": [0.5, 0.5],
                    "metadata": {"file_type": ".txt", "section": "setup"},
                },
            ]

            # Test file type filtering
            results_md = engine.query_docs("system", top_k=10, file_type_filter=".md")
            self.assertTrue(all(r["file"].endswith(".md") for r in results_md))

            # Test file name filtering
            results_arch = engine.query_docs("system", top_k=10, file_filter="architecture")
            self.assertTrue(all("architecture" in r["file"].lower() for r in results_arch))

    @patch("google.genai.Client")
    def test_semantic_chunking(self, mock_client_class):
        """Verifies that semantic chunking respects paragraph boundaries."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.values = [0.1, 0.2]
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response
        mock_client_class.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            engine = DocSearchEngine()

            # Test semantic chunking with paragraphs
            content = "First paragraph with some text.\n\nSecond paragraph with different content.\n\nThird paragraph."
            chunks = engine._split_into_semantic_chunks(content, max_chunk_size=50)

            # Should respect paragraph boundaries
            self.assertTrue(len(chunks) >= 2)  # At least 2 chunks for 3 paragraphs
            # Each chunk should be reasonably sized
            for chunk in chunks:
                self.assertLessEqual(len(chunk), 50 + 20)  # Allow some overflow

    @patch("google.genai.Client")
    def test_mmr_diversification(self, mock_client_class):
        """Verifies that MMR diversification reduces duplicate results."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            engine = DocSearchEngine()

            # Create similar documents (high similarity)
            engine.docs_index = [
                {
                    "file_name": "similar1.md",
                    "sentence": "Cost optimization strategies for cloud resources.",
                    "vector": [0.9, 0.1, 0.0],
                },
                {
                    "file_name": "similar2.md",
                    "sentence": "Cost optimization techniques for cloud infrastructure.",
                    "vector": [0.89, 0.11, 0.0],  # Very similar to first
                },
                {
                    "file_name": "different.md",
                    "sentence": "Network security configuration best practices.",
                    "vector": [0.1, 0.1, 0.8],  # Different topic
                },
            ]

            # Test MMR with high diversity preference
            results = [(0, 0.9), (1, 0.89), (2, 0.8)]  # Initial rankings
            diverse_results = engine._apply_maximal_marginal_relevance(
                results, lambda_param=0.3, top_k=2
            )

            # With lambda=0.3 (diversity preference), should pick different document
            selected_indices = [idx for idx, _ in diverse_results]
            self.assertIn(2, selected_indices)  # Different document should be selected

    @patch("google.genai.Client")
    def test_get_document_context_safely(self, mock_client_class):
        """Verifies Claude-style situating document context generation is accurate."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            engine = DocSearchEngine()

            content = (
                "# Cloud-Reaper System Architecture\n\nThis is the core design philosophy details."
            )
            context = engine.get_document_context_safely("docs/architecture.md", content)

            # Verify global title and paragraph are present
            self.assertIn("Document: architecture.md", context)
            self.assertIn("Title: Cloud-Reaper System Architecture", context)
            self.assertIn("Summary:", context)
            self.assertIn("design philosophy", context)


class TestEmbedWithBackoff(unittest.TestCase):
    """Unit tests for _embed_with_backoff: 429 circuit-breaker and 503 retry logic."""

    def _make_engine(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake"}):
            with patch("google.genai.Client"):
                return DocSearchEngine()

    # ------------------------------------------------------------------
    # 429 RESOURCE_EXHAUSTED — should flip the circuit-breaker immediately
    # ------------------------------------------------------------------

    def test_429_sets_quota_exhausted_and_returns_none(self):
        engine = self._make_engine()
        engine.client.models.embed_content.side_effect = Exception(
            "429 RESOURCE_EXHAUSTED retryDelay30s"
        )

        result = engine._embed_with_backoff("some content")

        self.assertIsNone(result, "Should return None on 429")
        self.assertTrue(engine._quota_exhausted, "Circuit-breaker must be set on 429")
        # Only ONE attempt — no retries allowed for quota exhaustion
        engine.client.models.embed_content.assert_called_once()

    def test_429_without_retry_delay_hint_still_sets_flag(self):
        engine = self._make_engine()
        engine.client.models.embed_content.side_effect = Exception("429 RESOURCE_EXHAUSTED")

        result = engine._embed_with_backoff("content")

        self.assertIsNone(result)
        self.assertTrue(engine._quota_exhausted)

    # ------------------------------------------------------------------
    # 503 UNAVAILABLE — should retry with backoff, then give up
    # ------------------------------------------------------------------

    @patch("reaper.rag.engine.time.sleep")
    def test_503_retries_then_gives_up(self, mock_sleep):
        engine = self._make_engine()
        engine.client.models.embed_content.side_effect = Exception("503 UNAVAILABLE")

        result = engine._embed_with_backoff("some content")

        self.assertIsNone(result, "Should return None after exhausting retries")
        self.assertFalse(engine._quota_exhausted, "Circuit-breaker must NOT be set for 503")
        # Should have been called _EMBED_MAX_RETRIES times
        self.assertEqual(
            engine.client.models.embed_content.call_count,
            DocSearchEngine._EMBED_MAX_RETRIES,
        )
        # sleep() should have been called for every attempt except the last
        self.assertEqual(mock_sleep.call_count, DocSearchEngine._EMBED_MAX_RETRIES - 1)

    @patch("reaper.rag.engine.time.sleep")
    def test_503_recovers_on_second_attempt(self, mock_sleep):
        engine = self._make_engine()
        mock_embedding = MagicMock()
        mock_embedding.values = [0.9, 0.8, 0.7]
        good_response = MagicMock()
        good_response.embeddings = [mock_embedding]

        # First call raises 503, second succeeds
        engine.client.models.embed_content.side_effect = [
            Exception("503 UNAVAILABLE"),
            good_response,
        ]

        result = engine._embed_with_backoff("content")

        self.assertEqual(result, [0.9, 0.8, 0.7], "Should return the vector on recovery")
        self.assertFalse(engine._quota_exhausted)
        self.assertEqual(engine.client.models.embed_content.call_count, 2)
        mock_sleep.assert_called_once()  # one back-off before the successful retry

    # ------------------------------------------------------------------
    # load_and_index_docs circuit-breaker — should stop all iteration
    # ------------------------------------------------------------------

    def test_load_and_index_docs_stops_on_quota_exhaustion(self):
        """Once 429 fires, no further embed_content calls should be made."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake"}):
            with patch("google.genai.Client"):
                engine = DocSearchEngine()

        mock_embedding = MagicMock()
        mock_embedding.values = [0.1, 0.2]
        good_response = MagicMock()
        good_response.embeddings = [mock_embedding]

        call_count = {"n": 0}

        def embed_side_effect(*_args, **_kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise Exception("429 RESOURCE_EXHAUSTED")
            return good_response

        engine.client.models.embed_content.side_effect = embed_side_effect

        # Use much longer content with sections to ensure multiple chunks with semantic chunking
        content = """# Doc
## Section 1
Short sentence one. Short sentence two. Short sentence three. Short sentence four. Short sentence five. Short sentence six. Short sentence seven. Short sentence eight. Short sentence nine. Short sentence ten.

## Section 2  
Another sentence one. Another sentence two. Another sentence three. Another sentence four. Another sentence five. Another sentence six. Another sentence seven. Another sentence eight. Another sentence nine. Another sentence ten.

## Section 3
More sentences here. More sentences there. More sentences everywhere. This should definitely create multiple chunks with the new semantic chunking approach that respects section boundaries."""

        with (
            patch("pathlib.Path.open", unittest.mock.mock_open(read_data=content)),
            patch("pathlib.Path.rglob", return_value=[Path("docs/test.md")]),
        ):
            engine.load_and_index_docs("docs")

        # The circuit-breaker fired on the 2nd call — only the 1st chunk should be indexed
        self.assertEqual(len(engine.docs_index), 1)
        self.assertTrue(engine._quota_exhausted)
        # No more than 2 API calls should have happened (1 success + 1 that triggered 429)
        self.assertLessEqual(call_count["n"], 2)

    def test_load_and_index_docs_resets_circuit_breaker_on_new_run(self):
        """Calling load_and_index_docs again must clear _quota_exhausted."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake"}):
            with patch("google.genai.Client"):
                engine = DocSearchEngine()

        # Manually set stale flag from a previous session
        engine._quota_exhausted = True

        mock_embedding = MagicMock()
        mock_embedding.values = [0.5, 0.5]
        good_response = MagicMock()
        good_response.embeddings = [mock_embedding]
        engine.client.models.embed_content.return_value = good_response

        content = "# Title\nOne clean sentence."

        with (
            patch("pathlib.Path.open", unittest.mock.mock_open(read_data=content)),
            patch("pathlib.Path.rglob", return_value=[Path("docs/clean.md")]),
        ):
            engine.load_and_index_docs("docs")

        # After a fresh indexing run the flag is reset and documents are indexed
        self.assertFalse(engine._quota_exhausted)
        self.assertGreater(len(engine.docs_index), 0)


class TestSearchRoutes(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        self.client = TestClient(app)
        self.first_run_patcher = patch("reaper.web.app_async.is_first_run", return_value=False)
        self.mock_first_run = self.first_run_patcher.start()

    def tearDown(self):
        self.first_run_patcher.stop()

    def test_docs_page(self):
        """Test that the /docs route renders successfully."""
        response = self.client.get("/docs")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Audit Logs &amp; Change Tracking", response.content)
        self.assertIn(b"Attribution Stability Index", response.content)

    @patch("reaper.web.search_router.search_engine")
    def test_handle_docs_search(self, mock_search_engine):
        """Test the /api/v1/docs/search endpoint."""
        mock_search_engine.query_docs.return_value = [
            {
                "file": "4_audit_logs.md",
                "content": "To maintain operational integrity and strict regulatory compliance, Cloud-Reaper includes a high-fidelity, comprehensive Audit Logging system.",
                "confidence_score": "95.50%",
                "metadata": {"file_type": ".md", "section": "audit"},
                "text": "To maintain operational integrity and strict regulatory compliance, Cloud-Reaper includes a high-fidelity, comprehensive Audit Logging system.",
                "score": 0.955,
                "metadata_frontend": {"filename": "4_audit_logs.md", "title": "Audit Logs"},
            }
        ]

        response = self.client.post(
            "/api/v1/docs/search",
            json={"query": "audit logs"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["file"], "4_audit_logs.md")
        self.assertIn("Audit Logging system", data["results"][0]["content"])
