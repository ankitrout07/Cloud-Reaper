# tests/unit/test_rag_search.py
import unittest
from unittest.mock import patch, MagicMock
from reaper.rag import DocSearchEngine

class TestDocSearchEngine(unittest.TestCase):
    @patch('google.genai.Client')
    @patch('glob.glob')
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="## Section A\nThis is architecture.\n## Section B\nThis is deployment.")
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

        with patch.dict('os.environ', {'GEMINI_API_KEY': 'fake_key'}):
            engine = DocSearchEngine()
            engine.load_and_index_docs("docs")

            # Check that two chunks were split and embedded
            self.assertEqual(len(engine.docs_index), 2)
            self.assertEqual(engine.docs_index[0]["file_name"], "architecture.md")
            self.assertEqual(engine.docs_index[0]["vector"], [0.1, 0.2, 0.3])

    @patch('google.genai.Client')
    def test_query_docs(self, mock_client_class):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_embedding = MagicMock()
        # Mock query vector
        mock_embedding.values = [1.0, 0.0]
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response
        mock_client_class.return_value = mock_client

        with patch.dict('os.environ', {'GEMINI_API_KEY': 'fake_key'}):
            engine = DocSearchEngine()
            # Directly populate index to avoid filesystem operations
            engine.docs_index = [
                {
                    "file_name": "architecture.md",
                    "text": "## Section A\nThis matches perfectly",
                    "vector": [1.0, 0.0]
                },
                {
                    "file_name": "deployment.md",
                    "text": "## Section B\nThis has zero similarity",
                    "vector": [0.0, 1.0]
                }
            ]

            results = engine.query_docs("perfect match", top_k=1)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["file"], "architecture.md")
            self.assertEqual(results[0]["confidence_score"], "100.00%")
