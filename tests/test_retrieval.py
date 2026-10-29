import pytest

from eval.retrieval_metrics import recall_at_k
from src.retrieval import Retriever

DOCS = [
    "the cat sat on the mat",
    "stock markets fell sharply today",
    "python is a programming language",
]
QUERIES = ["cat on the mat", "markets fell today", "programming language python"]


def test_numpy_mock_recall():
    r = Retriever(backend="numpy", provider="mock")
    r.add(DOCS)
    assert recall_at_k(r, QUERIES, DOCS, k=1) == 1.0


def test_search_is_deterministic():
    a = Retriever(provider="mock")
    b = Retriever(provider="mock")
    a.add(DOCS)
    b.add(DOCS)
    assert a.search("markets", k=3) == b.search("markets", k=3)


def test_chroma_matches_numpy():
    pytest.importorskip("chromadb")
    a = Retriever(backend="numpy", provider="mock")
    b = Retriever(backend="chroma", provider="mock")
    a.add(DOCS)
    b.add(DOCS)
    for q in QUERIES:
        assert a.search(q, k=1)[0][0] == b.search(q, k=1)[0][0]


def test_local_embeddings_are_semantic():
    pytest.importorskip("sentence_transformers")
    r = Retriever(backend="numpy", provider="local")
    r.add(DOCS)
    assert r.search("financial markets dropped", k=1)[0][0] == DOCS[1]
