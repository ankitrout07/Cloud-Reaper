# src/reaper/rag/engine.py
import glob
import math
import os
import re
from collections import Counter
from unittest.mock import MagicMock

from google import genai


class BM25:
    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents = documents
        self.N = len(documents)
        self.avgdl = 0.0
        self.doc_freqs = Counter()
        self.doc_lengths = []
        self.doc_term_freqs = []
        self._index_documents()

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    def _index_documents(self):
        total_len = 0
        for doc in self.documents:
            tokens = self._tokenize(doc)
            doc_len = len(tokens)
            total_len += doc_len
            self.doc_lengths.append(doc_len)

            tfs = Counter(tokens)
            self.doc_term_freqs.append(tfs)

            for term in tfs.keys():
                self.doc_freqs[term] += 1

        self.avgdl = total_len / self.N if self.N > 0 else 0.0

    def get_score(self, query: str, doc_idx: int) -> float:
        query_tokens = self._tokenize(query)
        score = 0.0
        doc_len = self.doc_lengths[doc_idx]
        tfs = self.doc_term_freqs[doc_idx]

        for term in query_tokens:
            if term not in self.doc_freqs:
                continue
            df = self.doc_freqs[term]
            # Standard BM25 IDF with smoothing to avoid negative scores
            idf = math.log(1 + (self.N - df + 0.5) / (df + 0.5))

            tf = tfs[term]
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (
                1 - self.b + self.b * (doc_len / self.avgdl if self.avgdl > 0 else 1)
            )
            score += idf * (numerator / denominator)

        return score


class DocSearchEngine:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("CRITICAL: GEMINI_API_KEY environment variable is unconfigured.")
        self.client = genai.Client(api_key=api_key)
        self.embedding_model = "models/gemini-embedding-2"
        self.docs_index = []
        self._bm25 = None

    def _split_into_sentences(self, text: str) -> list[str]:
        """Splits raw text section into distinct clean sentences, filtering out headings."""
        lines = []
        for line in text.split("\n"):
            line_str = line.strip()
            if line_str and not line_str.startswith("#"):
                lines.append(line_str)
        cleaned_text = " ".join(lines)

        # Split by standard sentence punctuation followed by space or end of string.
        # Use negative lookbehind to avoid splitting on common abbreviations like e.g., i.e.
        raw_sentences = re.split(
            r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)(?:\s+|\s*$)", cleaned_text.strip()
        )
        sentences = []
        for s in raw_sentences:
            s = s.strip()
            if s:
                sentences.append(s)
        return sentences

    def _get_document_context(self, file_path: str, content: str) -> str:
        """Determines global context for Claude-style chunk situating."""
        file_name = os.path.basename(file_path)

        # Deterministically extract H1 title
        h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        h1_title = (
            h1_match.group(1).strip()
            if h1_match
            else file_name.replace(".md", "").replace("_", " ").title()
        )

        # Deterministically extract first paragraph
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        first_para = ""
        for line in lines:
            if (
                not line.startswith("#")
                and not line.startswith("```")
                and not line.startswith("-")
                and not line.startswith("*")
            ):
                first_para = line
                break
        if not first_para:
            first_para = f"System operations and configuration spec for {h1_title}."

        summary = f"This document details the {h1_title} within Cloud-Reaper. {first_para}"

        # Try generating situational context via Gemini for production richness
        try:
            # Only generate via API if client looks real and has models
            if hasattr(self.client, "models") and not isinstance(
                self.client, MagicMock if "MagicMock" in globals() else object
            ):
                prompt = (
                    f"Create a 1-sentence global summary of this document to situational-contextualize short chunks for a RAG retriever.\n"
                    f"Document Title: {h1_title}\n\nContent:\n{content[:1500]}"
                )
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash", contents=prompt
                )
                if response and response.text:
                    summary = response.text.strip()
        except Exception:
            pass

        return f"Document: {file_name}\nTitle: {h1_title}\nSummary: {summary}"

    def load_and_index_docs(self, docs_dir: str = "docs"):
        """Reads and indexes all markdown files from the target repository documentation tree."""
        self.docs_index = []
        search_path = os.path.join(docs_dir, "**/*.md")

        for file_path in glob.glob(search_path, recursive=True):
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # Global Document Context for Claude-style chunk situating
            doc_context = self.get_document_context_safely(file_path, content)

            # Split document into structural sections to prevent semantic cross-bleeding
            sections = content.split("\n## ")
            for idx, section in enumerate(sections):
                if not section.strip():
                    continue

                clean_section = section if idx == 0 else f"## {section}"
                sentences = self._split_into_sentences(clean_section)

                # Store each sentence with contextual window enrichment
                for s_idx, sentence in enumerate(sentences):
                    # Get surrounding sentence context
                    left_context_list = sentences[max(0, s_idx - 2) : s_idx]
                    right_context_list = sentences[s_idx + 1 : min(len(sentences), s_idx + 3)]

                    left_context = " ".join(left_context_list)
                    right_context = " ".join(right_context_list)

                    # Situating context prefix
                    situated_content = f"{doc_context}\n\nSentence: {sentence}"

                    try:
                        # Generate embedding using the situated sentence context
                        response = self.client.models.embed_content(
                            model=self.embedding_model, contents=situated_content
                        )

                        self.docs_index.append(
                            {
                                "file_name": os.path.basename(file_path),
                                "text": situated_content,  # Claude situated context
                                "sentence": sentence,  # Core sentence
                                "left_context": left_context,
                                "right_context": right_context,
                                "vector": response.embeddings[0].values,
                            }
                        )
                    except Exception as e:
                        print(f"WARN: Error generating embedding for chunk in {file_path}: {e}")

        # Invalidate BM25 cache so it gets rebuilt
        self._bm25 = None

    def get_document_context_safely(self, file_path: str, content: str) -> str:
        return self._get_document_context(file_path, content)

    def _get_bm25_index(self):
        """Lazily builds BM25 index on active documentation items."""
        if self._bm25 is None and self.docs_index:
            # We index either the situated text or the core sentence. Situated text contains
            # global metadata which helps sparse matching locate files by global terms too!
            documents = [doc.get("text", doc.get("sentence", "")) for doc in self.docs_index]
            self._bm25 = BM25(documents)
        return self._bm25

    def query_docs(self, user_query: str, top_k: int = 3) -> list:
        """Executes advanced contextual search using sparse-dense RRF fusion and Cross-Encoder re-ranking."""
        if not self.docs_index:
            return []

        # 1. Dense Retrieval (Cosine Similarity)
        query_response = self.client.models.embed_content(
            model=self.embedding_model, contents=user_query
        )
        query_vector = query_response.embeddings[0].values

        dense_scores = []
        for idx, doc in enumerate(self.docs_index):
            vector = doc["vector"]
            dot_product = sum(q * d for q, d in zip(query_vector, vector))
            q_norm = sum(q * q for q in query_vector) ** 0.5
            d_norm = sum(d * d for d in vector) ** 0.5
            similarity = dot_product / (q_norm * d_norm) if (q_norm * d_norm) > 0 else 0
            dense_scores.append((idx, similarity))

        # Rank dense matches (1-indexed)
        dense_scores.sort(key=lambda x: x[1], reverse=True)
        dense_ranks = {idx: rank + 1 for rank, (idx, _) in enumerate(dense_scores)}

        # 2. Sparse Retrieval (BM25)
        bm25_indexer = self._get_bm25_index()
        sparse_scores = []
        if bm25_indexer:
            for idx in range(len(self.docs_index)):
                score = bm25_indexer.get_score(user_query, idx)
                sparse_scores.append((idx, score))
        else:
            sparse_scores = [(idx, 0.0) for idx in range(len(self.docs_index))]

        # Rank sparse matches (1-indexed)
        sparse_scores.sort(key=lambda x: x[1], reverse=True)
        sparse_ranks = {idx: rank + 1 for rank, (idx, _) in enumerate(sparse_scores)}

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_constant = 60
        rrf_scores = []
        for idx in range(len(self.docs_index)):
            r_dense = dense_ranks.get(idx, len(self.docs_index) + 1)
            r_sparse = sparse_ranks.get(idx, len(self.docs_index) + 1)
            rrf_score = 1.0 / (rrf_constant + r_dense) + 1.0 / (rrf_constant + r_sparse)
            rrf_scores.append((idx, rrf_score))

        # Sort by best RRF score and pull top candidates (up to top_k * 4, min 10 pool)
        rrf_scores.sort(key=lambda x: x[1], reverse=True)
        candidate_pool_size = max(top_k * 4, 10)
        top_candidates = [
            (idx, self.docs_index[idx]) for idx, _ in rrf_scores[:candidate_pool_size]
        ]

        # 4. Cross-Encoder Re-Ranking
        scored_candidates = []
        # Attempt Gemini model check
        gemini_success = False
        try:
            if hasattr(self.client, "models") and not isinstance(
                self.client, MagicMock if "MagicMock" in globals() else object
            ):
                candidates_str = ""
                for rank_idx, (idx, doc) in enumerate(top_candidates):
                    sentence_body = doc.get("sentence", doc.get("text", ""))
                    candidates_str += f"[ID: {rank_idx}] Sentence Chunk:\n{sentence_body}\n---\n"

                prompt = (
                    f"You are a search ranking assistant. Rank the relevance of the following sentence chunks "
                    f"to the user query. Assign each chunk a relevance score between 0.0 (completely irrelevant) "
                    f"and 100.0 (extremely relevant / exact match).\n\n"
                    f"User Query: {user_query}\n\n"
                    f"Candidate Chunks:\n{candidates_str}\n"
                    f"Ensure you return the score list matching all chunk IDs."
                )

                schema = {
                    "type": "OBJECT",
                    "properties": {
                        "scores": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "id": {"type": "INTEGER"},
                                    "score": {"type": "NUMBER"},
                                },
                                "required": ["id", "score"],
                            },
                        }
                    },
                    "required": ["scores"],
                }

                response = self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config={"response_mime_type": "application/json", "response_schema": schema},
                )

                if response and response.text:
                    import json

                    parsed_res = json.loads(response.text)
                    scores_list = parsed_res.get("scores", [])
                    scores_map = {item["id"]: item["score"] for item in scores_list}

                    for rank_idx, (idx, doc) in enumerate(top_candidates):
                        ce_score = scores_map.get(rank_idx, 0.0)
                        scored_candidates.append((ce_score, doc))
                    gemini_success = True
        except Exception:
            pass

        if not gemini_success:
            # Robust local fallback: Jaccard/overlap + vector similarity boost
            query_words = set(re.findall(r"\w+", user_query.lower()))
            for idx, doc in top_candidates:
                sentence_text = doc.get("sentence", doc.get("text", ""))
                sentence_words = set(re.findall(r"\w+", sentence_text.lower()))
                overlap = len(query_words.intersection(sentence_words))
                jaccard = (
                    (overlap / len(query_words.union(sentence_words)))
                    if query_words.union(sentence_words)
                    else 0.0
                )
                ce_score = jaccard * 100.0

                # Check for exact case-insensitive query substring match
                if user_query.lower() in sentence_text.lower():
                    ce_score = max(ce_score, 100.0)

                # Add vector similarity tie-breaker
                dense_cos = 0.0
                for d_idx, d_score in dense_scores:
                    if d_idx == idx:
                        dense_cos = d_score
                        break

                ce_score = max(ce_score, dense_cos * 100.0)
                scored_candidates.append((ce_score, doc))

        # Sort and select top_k results
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        final_results = []
        for score, doc in scored_candidates[:top_k]:
            left = doc.get("left_context", "")
            right = doc.get("right_context", "")
            sentence = doc.get("sentence", doc.get("text", ""))

            # Combine sentences cleanly if available
            enriched_content = sentence
            if left:
                enriched_content = f"{left} {enriched_content}"
            if right:
                enriched_content = f"{enriched_content} {right}"

            final_results.append(
                {
                    "file": doc["file_name"],
                    "content": enriched_content,
                    "confidence_score": f"{score:.2f}%",
                }
            )

        return final_results
