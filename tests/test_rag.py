import src.rag as rag
from src.rag import RagAnswer, build_prompt, rag_answer
from src.retrieval import Retriever

DOCS = [
    "the cat sat on the mat",
    "stock markets fell sharply today",
    "python is a programming language",
]


def make_retriever():
    r = Retriever(provider="mock")
    r.add(DOCS)
    return r


def test_rag_pipeline_with_mock_llm():
    out, passages = rag_answer("what fell today", make_retriever(), k=2)
    assert isinstance(out, RagAnswer)
    assert out.degraded is False
    assert len(passages) == 2
    assert passages[0] == DOCS[1]


def test_falls_back_when_llm_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(rag, "ask_json", boom)
    out, passages = rag_answer("what fell today", make_retriever(), k=2)
    assert out.degraded is True
    assert out.answer == DOCS[1]


def test_prompt_numbers_the_context():
    p = build_prompt("q", ["a", "b"])
    assert "[1] a" in p and "[2] b" in p
