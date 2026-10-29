import hashlib
import os

import numpy as np

_MODEL = None


def _mock(texts, dim=64):
    out = np.zeros((len(texts), dim), dtype=np.float32)
    for i, text in enumerate(texts):
        for tok in text.lower().split():
            h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
            out[i, h % dim] += 1.0
    return out


def embed(texts, provider=None):
    provider = provider or os.getenv("EMBED_PROVIDER", "mock")
    texts = list(texts)
    if provider == "mock":
        vecs = _mock(texts)
    elif provider == "local":
        global _MODEL
        if _MODEL is None:
            from sentence_transformers import SentenceTransformer
            name = os.getenv("EMBED_MODEL") or "all-MiniLM-L6-v2"
            try:
                _MODEL = SentenceTransformer(name, local_files_only=True)
            except (OSError, ValueError):
                _MODEL = SentenceTransformer(name)
        vecs = _MODEL.encode(texts, convert_to_numpy=True)
    else:
        raise ValueError(f"Unknown EMBED_PROVIDER: {provider}")
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms
