"""
Embedding model wrapper.

Uses sentence-transformers/all-MiniLM-L6-v2, a free, self-hosted model
(~80MB, runs on CPU). No API key, no per-call cost - this keeps RepoMind
fully usable without any paid API, at the cost of slightly lower embedding
quality than a large hosted model like OpenAI's text-embedding-3.

The model is loaded once (module-level singleton) so repeated ingestion or
query calls don't reload weights from disk each time.
"""

from functools import lru_cache

import numpy as np


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a batch of texts. Returns an (N, 384) float32 array, L2-normalized
    so that inner product search is equivalent to cosine similarity."""
    model = _get_model()
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    return embeddings.astype("float32")


def embed_query(query: str) -> np.ndarray:
    return embed_texts([query])[0]
