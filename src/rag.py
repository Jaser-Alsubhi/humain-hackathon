import logging

from pydantic import BaseModel

from src.llm import ask_json

log = logging.getLogger(__name__)


class RagAnswer(BaseModel):
    answer: str
    sources: list[int] = []
    degraded: bool = False


SYSTEM = (
    "Answer using only the numbered context. If the context does not contain "
    "the answer, say you do not know. Return JSON with keys answer (string) "
    "and sources (list of the context numbers you used)."
)


def build_prompt(question, passages):
    ctx = "\n".join(f"[{i}] {p}" for i, p in enumerate(passages, 1))
    return f"Context:\n{ctx}\n\nQuestion: {question}"


def rag_answer(question, retriever, k=3):
    hits = retriever.search(question, k)
    passages = [doc for doc, _ in hits]
    try:
        out = ask_json(build_prompt(question, passages), RagAnswer, system=SYSTEM)
    except (RuntimeError, ValueError) as err:
        log.warning("LLM unavailable, using extractive fallback: %s", err)
        out = RagAnswer(answer=passages[0], sources=[1], degraded=True)
    return out, passages
