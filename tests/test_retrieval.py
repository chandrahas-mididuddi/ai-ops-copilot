from ai_ops_copilot.corpus import load_docs
from ai_ops_copilot.retrieval import BM25, HybridRetriever


def test_bm25_ranks_relevant_doc_first(docs):
    bm25 = BM25(docs)
    scores = bm25.score("checkout api p95 latency high")
    top = docs[scores.index(max(scores))]
    assert top.id == "doc-checkout-latency"


def test_bm25_empty_query_scores_zero(docs):
    bm25 = BM25(docs)
    assert all(s == 0.0 for s in bm25.score(""))


def test_hybrid_search_returns_top_k_with_citations(docs):
    retriever = HybridRetriever(docs)
    results = retriever.search("payments gateway 5xx errors deploy", top_k=3)
    # Only two docs share any terms with this query; both must rank.
    assert len(results) == 2
    assert results[0].doc.id == "doc-payments-errors"
    assert all(0.0 <= r.score <= 1.0 for r in results)
    assert all(0.0 <= r.bm25 <= 1.0 and 0.0 <= r.tfidf <= 1.0 for r in results)


def test_hybrid_search_scores_descending(docs):
    retriever = HybridRetriever(docs)
    results = retriever.search("inventory sync consumer lag", top_k=3)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    assert results[0].doc.id == "doc-inventory-lag"


def test_hybrid_search_empty_query(docs):
    retriever = HybridRetriever(docs)
    assert retriever.search("   ") == []


def test_hybrid_search_unknown_terms_returns_nothing(docs):
    retriever = HybridRetriever(docs)
    assert retriever.search("zebra quantum banana") == []


def test_docs_load_all_fictional(docs):
    assert len(docs) == 12
    assert {d.service for d in docs} >= {
        "checkout-api",
        "payments-gateway",
        "inventory-sync",
        "pricing-engine",
    }
