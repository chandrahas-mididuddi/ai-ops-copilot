"""Hybrid retrieval: BM25 + TF-IDF cosine similarity.

Both rankers are implemented on the fictional docs corpus. Scores are
min-max normalised per query and combined with a configurable weight, so
the hybrid score is always in [0, 1]. No network, no external model.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .corpus import Doc

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass(frozen=True)
class RetrievalResult:
    doc: Doc
    bm25: float
    tfidf: float
    score: float


class BM25:
    """Minimal BM25 (k1=1.5, b=0.75) over a list of documents."""

    def __init__(self, docs: list[Doc], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1 = k1
        self.b = b
        self._doc_tokens = [tokenize(doc.text) for doc in docs]
        self._doc_lens = [len(tokens) for tokens in self._doc_tokens]
        self._avg_len = sum(self._doc_lens) / max(len(self._doc_lens), 1)
        self._df: dict[str, int] = {}
        for tokens in self._doc_tokens:
            for token in set(tokens):
                self._df[token] = self._df.get(token, 0) + 1

    def _idf(self, token: str) -> float:
        n = len(self.docs)
        df = self._df.get(token, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def score(self, query: str) -> list[float]:
        query_tokens = tokenize(query)
        scores: list[float] = []
        for i, tokens in enumerate(self._doc_tokens):
            tf: dict[str, int] = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            total = 0.0
            for token in set(query_tokens):
                if token not in tf:
                    continue
                f = tf[token]
                denom = f + self.k1 * (
                    1 - self.b + self.b * self._doc_lens[i] / self._avg_len
                )
                total += self._idf(token) * f * (self.k1 + 1) / denom
            scores.append(total)
        return scores


class HybridRetriever:
    """BM25 + TF-IDF retrieval over the docs corpus."""

    def __init__(self, docs: list[Doc], bm25_weight: float = 0.5):
        self.docs = docs
        self.bm25_weight = bm25_weight
        self._bm25 = BM25(docs)
        self._vectorizer = TfidfVectorizer(token_pattern=r"[a-z0-9]+")
        self._matrix = self._vectorizer.fit_transform(
            [doc.text for doc in docs]
        )

    @staticmethod
    def _normalise(scores: list[float]) -> list[float]:
        top = max(scores) if scores else 0.0
        if top <= 0:
            return [0.0 for _ in scores]
        return [s / top for s in scores]

    def search(self, query: str, top_k: int = 3) -> list[RetrievalResult]:
        if not query.strip():
            return []
        bm25_scores = self._normalise(self._bm25.score(query))
        query_vec = self._vectorizer.transform([query])
        tfidf_scores = self._normalise(
            cosine_similarity(query_vec, self._matrix)[0].tolist()
        )
        results = [
            RetrievalResult(
                doc=doc,
                bm25=round(b, 4),
                tfidf=round(t, 4),
                score=round(
                    self.bm25_weight * b + (1 - self.bm25_weight) * t, 4
                ),
            )
            for doc, b, t in zip(self.docs, bm25_scores, tfidf_scores)
        ]
        results.sort(key=lambda r: r.score, reverse=True)
        return [r for r in results[:top_k] if r.score > 0]
