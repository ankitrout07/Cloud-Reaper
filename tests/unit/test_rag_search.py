# tests/unit/test_rag_search.py
import unittest
from unittest.mock import MagicMock, patch

from reaper.rag import DocSearchEngine
from reaper.web.app import app


class TestDocSearchEngine(unittest.TestCase):
    @patch("google.genai.Client")
    @patch("glob.glob")
    @patch(
        "builtins.open",
        new_callable=unittest.mock.mock_open,
        read_data="## Section A\nThis is architecture.\n## Section B\nThis is deployment.",
    )
    def test_load_and_index_docs(self, mock_file, mock_glob, mock_client_class):
        # Setup mocks
        mock_glob.return_value = ["docs/architecture.md"]

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
        """Verifies that multi-sentence sections are split and enriched with left/right context."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.values = [0.1, 0.2]
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response
        mock_client_class.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_key"}):
            engine = DocSearchEngine()
            # Feed multi-sentence content
            content = "# Title\nThis is sentence one. This is sentence two. This is sentence three."

            with patch("builtins.open", unittest.mock.mock_open(read_data=content)):
                with patch("glob.glob", return_value=["docs/telemetry.md"]):
                    engine.load_and_index_docs("docs")

            # Check that three sentences were split
            self.assertEqual(len(engine.docs_index), 3)

            # First sentence check
            self.assertEqual(engine.docs_index[0]["sentence"], "This is sentence one.")
            self.assertEqual(engine.docs_index[0]["left_context"], "")
            self.assertEqual(
                engine.docs_index[0]["right_context"],
                "This is sentence two. This is sentence three.",
            )

            # Second sentence check
            self.assertEqual(engine.docs_index[1]["sentence"], "This is sentence two.")
            self.assertEqual(engine.docs_index[1]["left_context"], "This is sentence one.")
            self.assertEqual(engine.docs_index[1]["right_context"], "This is sentence three.")

            # Third sentence check
            self.assertEqual(engine.docs_index[2]["sentence"], "This is sentence three.")
            self.assertEqual(
                engine.docs_index[2]["left_context"], "This is sentence one. This is sentence two."
            )
            self.assertEqual(engine.docs_index[2]["right_context"], "")

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
        """Verifies that the Cross-Encoder fallback works offline and ranks correctly."""
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
            self.assertEqual(results[0]["confidence_score"], "100.00%")

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


class TestSearchRoutes(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        app.config["SECRET_KEY"] = "test-secret-key"
        self.client = app.test_client()
        self.first_run_patcher = patch("reaper.web.app.is_first_run", return_value=False)
        self.mock_first_run = self.first_run_patcher.start()

    def tearDown(self):
        self.first_run_patcher.stop()

    def test_docs_page(self):
        """Test that the /docs route renders successfully."""
        response = self.client.get("/docs")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Audit Logs &amp; Change Tracking", response.data)
        self.assertIn(b"Attribution Stability Index", response.data)

    @patch("reaper.web.search_routes.search_engine")
    def test_handle_docs_search(self, mock_search_engine):
        """Test the /api/v1/docs/search endpoint."""
        mock_search_engine.query_docs.return_value = [
            {
                "file": "4_audit_logs.md",
                "content": "To maintain operational integrity and strict regulatory compliance, Cloud-Reaper includes a high-fidelity, comprehensive Audit Logging system.",
                "confidence_score": "95.50%"
            }
        ]
        
        response = self.client.post(
            "/api/v1/docs/search",
            json={"query": "audit logs"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["file"], "4_audit_logs.md")
        self.assertIn("Audit Logging system", data["results"][0]["content"])
