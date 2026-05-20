# src/reaper/rag/engine.py
import os
import glob
from google import genai
from google.genai import types

class DocSearchEngine:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("CRITICAL: GEMINI_API_KEY environment variable is unconfigured.")
        self.client = genai.Client(api_key=api_key)
        self.embedding_model = "models/gemini-embedding-2" # Standard structural text embedding generation model
        self.docs_index = []

    def load_and_index_docs(self, docs_dir: str = "docs"):
        """Reads and indexes all markdown files from the target repository documentation tree."""
        self.docs_index = []
        search_path = os.path.join(docs_dir, "**/*.md")
        
        for file_path in glob.glob(search_path, recursive=True):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Naive chunking strategy split by structural section headers
            chunks = content.split("\n## ")
            for idx, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                
                clean_chunk = chunk if idx == 0 else f"## {chunk}"
                # Generate embedding vectors for this specific document block
                try:
                    response = self.client.models.embed_content(
                        model=self.embedding_model,
                        contents=clean_chunk
                    )
                    
                    self.docs_index.append({
                        "file_name": os.path.basename(file_path),
                        "text": clean_chunk,
                        "vector": response.embeddings[0].values
                    })
                except Exception as e:
                    print(f"WARN: Error generating embedding for chunk in {file_path}: {e}")

    def query_docs(self, user_query: str, top_k: int = 3) -> list:
        """Executes a contextual vector similarity search against the indexed document arrays."""
        if not self.docs_index:
            return []

        # Generate embedding vector for the inbound search query
        query_response = self.client.models.embed_content(
            model=self.embedding_model,
            contents=user_query
        )
        query_vector = query_response.embeddings[0].values

        # Perform a mathematical Cosine Similarity cross-reference calculation
        scored_results = []
        for doc in self.docs_index:
            dot_product = sum(q * d for q, d in zip(query_vector, doc["vector"]))
            q_norm = sum(q * q for q in query_vector) ** 0.5
            d_norm = sum(d * d for d in doc["vector"]) ** 0.5
            
            similarity = dot_product / (q_norm * d_norm) if (q_norm * d_norm) > 0 else 0
            scored_results.append((similarity, doc))

        # Sort by highest match percentage and return top matches
        scored_results.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "file": item[1]["file_name"],
                "content": item[1]["text"][:300] + "...", # Snip preview string length
                "confidence_score": f"{item[0] * 100:.2f}%"
            }
            for item in scored_results[:top_k]
        ]
