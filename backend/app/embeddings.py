"""
Embedding model wrapper.

Uses sentence-transformers/all-MiniLM-L6-v2, a free, self-hosted model
(~80MB, runs on CPU). No API key, no per-call cost - this keeps RepoMind
fully usable without any paid API, at the cost of slightly lower embedding
quality than a large hosted model like OpenAI's text-embedding-3.

Production note: loading sentence-transformers pulls in torch, which is
memory-heavy enough to exceed a free-tier host's RAM (e.g. Render's free
512MB instance) when combined with everything else the process is already
holding - the process gets OOM-killed outright, which no try/except inside
Python can catch, since the OS kills the process, not raises an exception.

To keep the service reliably up on constrained hosts, set the
PIPELINEGUARD_DISABLE_EMBEDDINGS=1 environment variable to skip loading the
model entirely and fall back to BM25-only retrieval (see retrieval.py).
This is a genuine, documented trade-off for the free-tier deployment, not
a silent degradation - it's called out in the product strategy write-up as
a "next step" (upgrade to a paid tier or a dedicated embedding endpoint) to
restore semantic retrieval.
"""

import os
from functools import lru_cache

import numpy as np

EMBEDDINGS_DISABLED = os.environ.get("PIPELINEGUARD_DISABLE_EMBEDDINGS", "").lower() in ("1", "true", "yes")


class EmbeddingsUnavailable(Exception):
    """Raised when embeddings are disabled or fail to load."""


@lru_cache(maxsize=1)
def _get_model():
    if EMBEDDINGS_DISABLED:
        raise EmbeddingsUnavailable("Embeddings disabled via PIPELINEGUARD_DISABLE_EMBEDDINGS.")
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a batch of texts. Returns an (N, 384) float32 array, L2-normalized
    so that inner product search is equivalent to cosine similarity.
    Raises EmbeddingsUnavailable if embeddings are disabled or fail to load -
    callers (see retrieval.HybridIndex) are expected to catch this and fall
    back to BM25-only search rather than letting it propagate."""
    try:
        model = _get_model()
    except Exception as e:
        raise EmbeddingsUnavailable(str(e)) from e
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
