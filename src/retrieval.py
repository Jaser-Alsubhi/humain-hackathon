import uuid

import numpy as np

from src.embed import embed


class Retriever:
    def __init__(self, backend="numpy", provider=None):
        self.backend = backend
        self.provider = provider
        self.docs = []
        self.vecs = None
        if backend == "chroma":
            import chromadb
            from chromadb.config import Settings
            client = chromadb.EphemeralClient(
                settings=Settings(anonymized_telemetry=False))
            self._col = client.create_collection(name="c" + uuid.uuid4().hex)
        elif backend != "numpy":
            raise ValueError(f"Unknown backend: {backend}")

    def add(self, docs):
        docs = list(docs)
        vecs = embed(docs, self.provider)
        if self.backend == "numpy":
            self.vecs = vecs if self.vecs is None else np.vstack([self.vecs, vecs])
        else:
            start = len(self.docs)
            self._col.add(
                ids=[str(start + i) for i in range(len(docs))],
                embeddings=vecs.tolist(),
                documents=docs)
        self.docs += docs

    def search(self, query, k=3):
        q = embed([query], self.provider)
        if self.backend == "numpy":
            scores = self.vecs @ q[0]
            idx = np.argsort(-scores, kind="stable")[:k]
            return [(self.docs[i], float(scores[i])) for i in idx]
        r = self._col.query(
            query_embeddings=q.tolist(), n_results=min(k, len(self.docs)))
        # Vectors are unit length, so squared L2 distance d gives cosine = 1 - d/2.
        return [(d, 1.0 - float(x) / 2.0)
                for d, x in zip(r["documents"][0], r["distances"][0])]
