"""Fictional internal documentation corpus.

Loads ``data/docs.yaml`` — runbooks and service docs for the fictional
company Meridian Retail. Nothing here is real: no employer data, no
production system, no proprietary documentation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import yaml

DEFAULT_DOCS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "docs.yaml",
)


@dataclass(frozen=True)
class Doc:
    id: str
    title: str
    service: str
    body: str

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body}"


def load_docs(path: str = DEFAULT_DOCS_PATH) -> list[Doc]:
    """Load the fictional docs corpus from YAML."""
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return [Doc(**item) for item in raw]


def services(docs: list[Doc]) -> list[str]:
    """Service names mentioned in the corpus, in first-seen order."""
    seen: list[str] = []
    for doc in docs:
        if doc.service not in seen:
            seen.append(doc.service)
    return seen
