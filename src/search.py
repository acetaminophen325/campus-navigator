"""
src/search.py

BM25 index over course titles and department names.

Each "document" in the index is a single Meeting, represented by its
title + dept concatenated as a short text field. At query time the index
returns a normalized relevance score in [0, 1] for every meeting, which
the ranker blends with time and distance scores.

BM25 parameters follow the standard Robertson et al. defaults:
  k1 = 1.5  (term-frequency saturation)
  b  = 0.75 (document-length normalization)
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Dict, List

from .models import Meeting


def _tokenize(text: str) -> List[str]:
    """Lowercase and split on non-alphanumeric characters."""
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


class BM25Index:
    """
    Inverted index with BM25 scoring.

    Build once at startup, then call score() on any query string.
    """

    K1 = 1.5
    B  = 0.75

    def __init__(self, meetings: List[Meeting]) -> None:
        self.meetings = meetings
        self._build(meetings)

    def _build(self, meetings: List[Meeting]) -> None:
        N = len(meetings)

        # term -> {doc_index -> term frequency}
        tf: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        doc_lengths: List[int] = []

        for idx, m in enumerate(meetings):
            tokens = _tokenize(f"{m.title} {m.dept}")
            doc_lengths.append(len(tokens))
            for tok in tokens:
                tf[tok][idx] += 1

        self._avgdl = sum(doc_lengths) / N if N else 1.0
        self._doc_lengths = doc_lengths

        # IDF for each term using the Robertson smooth formula
        self._idf: Dict[str, float] = {}
        for term, postings in tf.items():
            df = len(postings)
            self._idf[term] = math.log((N - df + 0.5) / (df + 0.5) + 1.0)

        self._tf = tf

    def scores(self, query: str) -> List[float]:
        """
        Return raw BM25 scores for all meetings in corpus order.
        Scores are non-negative but not yet normalized.
        """
        tokens = _tokenize(query)
        if not tokens:
            return [0.0] * len(self.meetings)

        raw = [0.0] * len(self.meetings)

        for tok in tokens:
            if tok not in self._idf:
                continue
            idf = self._idf[tok]
            for idx, freq in self._tf[tok].items():
                dl   = self._doc_lengths[idx]
                denom = freq + self.K1 * (1.0 - self.B + self.B * dl / self._avgdl)
                raw[idx] += idf * (freq * (self.K1 + 1.0)) / denom

        return raw

    def normalized_scores(self, query: str) -> List[float]:
        """
        Return BM25 scores normalized to [0, 1] by the corpus maximum.
        If no query terms match anything, all scores are 0.
        """
        raw = self.scores(query)
        max_raw = max(raw) if raw else 0.0
        if max_raw == 0.0:
            return raw
        return [v / max_raw for v in raw]

    def score_map(self, query: str) -> Dict[str, float]:
        """
        Return {meeting_id: normalized_score} for all meetings.
        Convenient for O(1) lookup by the ranker.
        """
        scores = self.normalized_scores(query)
        return {m.meeting_id: s for m, s in zip(self.meetings, scores)}
