"""
Hybrid retrieval: BM25 (lexical) + FAISS (semantic), combined via
reciprocal rank fusion (RRF).

Why hybrid instead of pure semantic search:
Code queries are often lexical - a question like "where is retry_with_backoff
called" is best answered by exact keyword match, which embeddings alone can
miss (semantically similar != exact identifier match). But a question like
"where do we handle transient network failures" needs semantic search, since
the function might be named `_retry` with no literal "network failure" text.
BM25 alone misses the second case; embeddings alone are weaker on the first.
Combining both and fusing rankings covers both query styles.

Why RRF instead of a weighted score average:
BM25 scores and cosine-similarity scores live on different, incomparable
scales, so a weighted average requires careful tuning to avoid one signal
dominating. RRF sidesteps this entirely by fusing on RANK rather than raw
score, which is simple, has no scale-mismatch problem, and is a well
established technique for combining heterogeneous retrievers.
"""

from dataclasses import dataclass

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

from .chunking import Chunk
from .embeddings import EmbeddingsUnavailable, embed_query, embed_texts


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float
    bm25_rank: int | None = None
    faiss_rank: int | None = None


def _tokenize_for_bm25(text: str) -> list[str]:
    # Simple whitespace/punctuation split. Code has meaningful punctuation
    # (e.g. snake_case, dots in method calls), so we keep it lightweight
    # rather than using a natural-language tokenizer that would strip it.
    import re
    return re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text.lower())


class HybridIndex:
    def __init__(self, chunks: list[Chunk]):
        if not chunks:
            raise ValueError("Cannot build an index from zero chunks.")
        self.chunks = chunks

        # --- BM25 index (always built - lightweight, pure Python) ---
        tokenized = [_tokenize_for_bm25(c.content) for c in chunks]
        self.bm25 = BM25Okapi(tokenized)

        # --- FAISS index (inner product = cosine sim, since embeddings are
        # normalized). This is optional: if embeddings are disabled (see
        # embeddings.py - PIPELINEGUARD_DISABLE_EMBEDDINGS) or fail to load
        # for any reason, we fall back to BM25-only search rather than
        # crashing the whole request. This matters most on memory-constrained
        # hosts, where loading the embedding model can push the process
        # over its RAM limit. */
        self.semantic_enabled = True
        self.faiss_index = None
        self.dim = None
        try:
            vectors = embed_texts([c.content for c in chunks])
            self.dim = vectors.shape[1]
            self.faiss_index = faiss.IndexFlatIP(self.dim)
            self.faiss_index.add(vectors)
        except EmbeddingsUnavailable:
            self.semantic_enabled = False

    def search(self, query: str, top_k: int = 8, rrf_k: int = 60) -> list[ScoredChunk]:
        # BM25 ranking
        bm25_scores = self.bm25.get_scores(_tokenize_for_bm25(query))
        bm25_ranked = np.argsort(bm25_scores)[::-1]

        if not self.semantic_enabled:
            # BM25-only fallback: no fusion needed, just take the top BM25
            # hits directly. Still fully functional for keyword-heavy
            # queries (e.g. "AsyncLimiter", "retry"), just without semantic
            # matching for queries phrased differently from the code.
            results = []
            for rank, idx in enumerate(bm25_ranked[:top_k]):
                results.append(ScoredChunk(
                    chunk=self.chunks[idx],
                    score=float(bm25_scores[idx]),
                    bm25_rank=rank + 1,
                    faiss_rank=None,
                ))
            return results

        # FAISS ranking
        q_vec = embed_query(query).reshape(1, -1)
        candidate_k = min(len(self.chunks), max(top_k * 5, 30))
        _, faiss_idx = self.faiss_index.search(q_vec, candidate_k)
        faiss_ranked = faiss_idx[0]

        # Reciprocal Rank Fusion: score(doc) = sum(1 / (rrf_k + rank))
        fused_scores: dict[int, float] = {}
        bm25_rank_map: dict[int, int] = {}
        faiss_rank_map: dict[int, int] = {}

        for rank, idx in enumerate(bm25_ranked[:candidate_k]):
            fused_scores[idx] = fused_scores.get(idx, 0.0) + 1.0 / (rrf_k + rank + 1)
            bm25_rank_map[idx] = rank + 1

        for rank, idx in enumerate(faiss_ranked):
            if idx == -1:
                continue
            fused_scores[idx] = fused_scores.get(idx, 0.0) + 1.0 / (rrf_k + rank + 1)
            faiss_rank_map[idx] = rank + 1

        ranked_ids = sorted(fused_scores.items(), key=lambda kv: kv[1], reverse=True)

        results = []
        for idx, score in ranked_ids[:top_k]:
            results.append(ScoredChunk(
                chunk=self.chunks[idx],
                score=score,
                bm25_rank=bm25_rank_map.get(idx),
                faiss_rank=faiss_rank_map.get(idx),
            ))
        return results
