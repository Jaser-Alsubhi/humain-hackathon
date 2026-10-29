def recall_at_k(retriever, queries, gold, k=3):
    hits = 0
    for query, answer in zip(queries, gold):
        got = [doc for doc, _ in retriever.search(query, k)]
        hits += answer in got
    return hits / len(queries)
