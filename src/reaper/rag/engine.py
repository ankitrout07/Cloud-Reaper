# src/reaper/rag/engine.py
import math
import random
import re
import time
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock

from google import genai


class BM25:
    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents = documents
        self.N = len(documents)
        self.avgdl: float = 0.0
        self.doc_freqs: Counter = Counter()
        self.doc_lengths: list[int] = []
        self.doc_term_freqs: list[Counter] = []
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

            for term in tfs:
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
    # Maximum retries for transient (5xx) embedding failures
    _EMBED_MAX_RETRIES: int = 3
    # Base backoff in seconds for exponential retry (jittered)
    _EMBED_BASE_BACKOFF: float = 1.5

    def __init__(self):
        import os

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("CRITICAL: GEMINI_API_KEY environment variable is unconfigured.")
        self.client = genai.Client(api_key=api_key)
        self.embedding_model = "models/gemini-embedding-2"
        self.docs_index = []
        self._bm25 = None
        # Circuit-breaker: set True when the API quota is exhausted (HTTP 429).
        # Prevents hammering the API with thousands of doomed requests per session.
        self._quota_exhausted: bool = False

    # ------------------------------------------------------------------
    # Embedding helper with retry / circuit-breaker logic
    # ------------------------------------------------------------------

    def _embed_with_backoff(self, content: str) -> list[float] | None:
        """Call the embedding API with exponential back-off for transient errors.

        Returns the embedding vector on success, or ``None`` if the chunk
        should be skipped (permanent error / quota exhausted).

        Side-effect: sets ``self._quota_exhausted = True`` when a 429 is
        encountered so the caller can stop all further embedding calls.
        """
        for attempt in range(self._EMBED_MAX_RETRIES):
            try:
                response = self.client.models.embed_content(
                    model=self.embedding_model, contents=content
                )
                return response.embeddings[0].values

            except Exception as exc:
                exc_str = str(exc)

                # ── 429 RESOURCE_EXHAUSTED ─────────────────────────────────
                # Quota is gone for this daily window.  Parse the suggested
                # retry delay (if present), log once, set the circuit-breaker
                # and return None immediately — no further retries.
                if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                    # Try to extract the retryDelay hint from the error payload
                    delay_match = re.search(r"retryDelay[^0-9]*([0-9]+)", exc_str)
                    delay_hint = delay_match.group(1) if delay_match else "unknown"
                    print(
                        f"WARN: Gemini embedding quota exhausted (429). "
                        f"Suggested retry delay: {delay_hint}s. "
                        "Disabling embedding for this session to avoid further quota burn."
                    )
                    self._quota_exhausted = True
                    return None

                # ── 503 UNAVAILABLE ───────────────────────────────────────
                # Transient service hiccup — back off and retry.
                if "503" in exc_str or "UNAVAILABLE" in exc_str:
                    if attempt < self._EMBED_MAX_RETRIES - 1:
                        backoff = self._EMBED_BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 0.5)
                        print(
                            f"WARN: Gemini embedding 503 (attempt {attempt + 1}/{self._EMBED_MAX_RETRIES}). "
                            f"Retrying in {backoff:.1f}s…"
                        )
                        time.sleep(backoff)
                        continue
                    # Final attempt also failed
                    print(f"WARN: Gemini embedding 503 – giving up after {self._EMBED_MAX_RETRIES} attempts.")
                    return None

                # ── Any other error ────────────────────────────────────────
                print(f"WARN: Embedding error (attempt {attempt + 1}): {exc}")
                return None

        return None

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
            s_clean = s.strip()
            if s_clean:
                sentences.append(s_clean)
        return sentences

    def _get_document_context(self, file_path: str, content: str) -> str:
        """Determines global context for Claude-style chunk situating."""
        file_name = Path(file_path).name

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
        """Reads and indexes all markdown files from the target repository documentation tree.

        Embedding calls are protected by an exponential-backoff retry for
        transient 503 errors and a session-level circuit-breaker for 429
        quota exhaustion — preventing unbounded API spam on rate-limit hits.
        """
        self.docs_index = []
        # Reset circuit-breaker at the start of every fresh indexing run
        self._quota_exhausted = False

        search_path = Path(docs_dir)
        if not search_path.exists():
            return

        for file_path in search_path.rglob("*.md"):
            # Stop processing further files once quota is blown for this session
            if self._quota_exhausted:
                print(
                    f"INFO: Skipping remaining docs — embedding quota exhausted. "
                    f"({file_path.name} and any subsequent files will not be indexed.)"
                )
                break

            with file_path.open(encoding="utf-8") as f:
                content = f.read()

            # Global Document Context for Claude-style chunk situating
            doc_context = self.get_document_context_safely(str(file_path), content)

            # Split document into structural sections to prevent semantic cross-bleeding
            sections = content.split("\n## ")
            file_quota_hit = False

            for idx, section in enumerate(sections):
                if file_quota_hit or self._quota_exhausted:
                    break
                if not section.strip():
                    continue

                clean_section = section if idx == 0 else f"## {section}"
                sentences = self._split_into_sentences(clean_section)

                # Store each sentence with contextual window enrichment
                for s_idx, sentence in enumerate(sentences):
                    if self._quota_exhausted:
                        file_quota_hit = True
                        break

                    left_context = " ".join(sentences[max(0, s_idx - 2) : s_idx])
                    right_context = " ".join(
                        sentences[s_idx + 1 : min(len(sentences), s_idx + 3)]
                    )
                    situated_content = f"{doc_context}\n\nSentence: {sentence}"

                    # Use backoff-aware helper — returns None on unrecoverable error
                    vector = self._embed_with_backoff(situated_content)
                    if vector is None:
                        # _quota_exhausted may have been set inside the helper
                        if self._quota_exhausted:
                            file_quota_hit = True
                        # Either way, skip this chunk and move on
                        continue

                    self.docs_index.append(
                        {
                            "file_name": file_path.name,
                            "text": situated_content,
                            "sentence": sentence,
                            "left_context": left_context,
                            "right_context": right_context,
                            "vector": vector,
                        }
                    )

        # Invalidate BM25 cache so it gets rebuilt on next query
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

    def _dense_search(self, user_query: str) -> list:
        query_response = self.client.models.embed_content(
            model=self.embedding_model, contents=user_query
        )
        query_vector = query_response.embeddings[0].values
        q_norm = sum(q * q for q in query_vector) ** 0.5

        dense_scores = []
        for idx, doc in enumerate(self.docs_index):
            vector = doc["vector"]
            dot_product = sum(q * d for q, d in zip(query_vector, vector, strict=False))
            d_norm = sum(d * d for d in vector) ** 0.5
            similarity = dot_product / (q_norm * d_norm) if (q_norm * d_norm) > 0 else 0
            dense_scores.append((idx, similarity))

        dense_scores.sort(key=lambda x: x[1], reverse=True)
        return dense_scores

    def _sparse_search(self, user_query: str) -> list:
        bm25_indexer = self._get_bm25_index()
        sparse_scores = []
        if bm25_indexer:
            for idx in range(len(self.docs_index)):
                sparse_scores.append((idx, bm25_indexer.get_score(user_query, idx)))
        else:
            sparse_scores = [(idx, 0.0) for idx in range(len(self.docs_index))]
        sparse_scores.sort(key=lambda x: x[1], reverse=True)
        return sparse_scores

    def _rerank_candidates_gemini(self, user_query: str, top_candidates: list) -> list:
        scored_candidates = []
        if not (
            hasattr(self.client, "models")
            and not isinstance(self.client, MagicMock if "MagicMock" in globals() else object)
        ):
            return []

        candidates_str = ""
        for rank_idx, (_, doc) in enumerate(top_candidates):
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

        try:
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

                for rank_idx, (_, doc) in enumerate(top_candidates):
                    ce_score = scores_map.get(rank_idx, 0.0)
                    scored_candidates.append((ce_score, doc))
        except Exception:
            return []
        return scored_candidates

    def _local_fallback_rerank(
        self, user_query: str, top_candidates: list, dense_scores: list
    ) -> list:
        scored_candidates = []
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

            if user_query.lower() in sentence_text.lower():
                ce_score = max(ce_score, 100.0)

            dense_cos = 0.0
            for d_idx, d_score in dense_scores:
                if d_idx == idx:
                    dense_cos = d_score
                    break

            ce_score = max(ce_score, dense_cos * 100.0)
            scored_candidates.append((ce_score, doc))
        return scored_candidates

    def query_docs(self, user_query: str, top_k: int = 3) -> list:
        """Executes advanced contextual search using sparse-dense RRF fusion and Cross-Encoder re-ranking."""
        if not self.docs_index:
            return []

        dense_scores = self._dense_search(user_query)
        dense_ranks = {idx: rank + 1 for rank, (idx, _) in enumerate(dense_scores)}

        sparse_scores = self._sparse_search(user_query)
        sparse_ranks = {idx: rank + 1 for rank, (idx, _) in enumerate(sparse_scores)}

        rrf_constant = 60
        rrf_scores = []
        for idx in range(len(self.docs_index)):
            r_dense = dense_ranks.get(idx, len(self.docs_index) + 1)
            r_sparse = sparse_ranks.get(idx, len(self.docs_index) + 1)
            rrf_scores.append(
                (idx, 1.0 / (rrf_constant + r_dense) + 1.0 / (rrf_constant + r_sparse))
            )

        rrf_scores.sort(key=lambda x: x[1], reverse=True)
        candidate_pool_size = max(top_k * 4, 10)
        top_candidates = [
            (idx, self.docs_index[idx]) for idx, _ in rrf_scores[:candidate_pool_size]
        ]

        scored_candidates = self._rerank_candidates_gemini(user_query, top_candidates)
        if not scored_candidates:
            scored_candidates = self._local_fallback_rerank(
                user_query, top_candidates, dense_scores
            )

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        final_results = []
        for score, doc in scored_candidates[:top_k]:
            left = doc.get("left_context", "")
            right = doc.get("right_context", "")
            sentence = doc.get("sentence", doc.get("text", ""))

            enriched_content = f"{left} {sentence}".strip() if left else sentence
            enriched_content = f"{enriched_content} {right}".strip() if right else enriched_content

            final_results.append(
                {
                    "file": doc["file_name"],
                    "content": enriched_content,
                    "confidence_score": f"{score:.2f}%",
                }
            )

        return final_results
