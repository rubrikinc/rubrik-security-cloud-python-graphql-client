"""
Field-level discovery for the RSC GraphQL schema.

The operation-level search in :mod:`rsc.index` ranks queries and mutations by
name, description, and the names of fields on the immediate return type. That
loses semantics nested deeper in the schema. For example, ``Group.activeUsers``
is described as "Users from the user group who are currently logged-in to the
account" -- the canonical answer to "who is logged in?" -- but the operation
that returns ``Group`` (``groupsInCurrentAndDescendantOrganization``) carries
none of that text in its own description.

:func:`search_fields` indexes every field on every object and interface type
and ranks them with BM25. The LLM (or any consumer) can then trace which
operations return that type via :func:`describe_type` /
:func:`search_operations`.

Example::

    from rsc import search_fields

    search_fields("logged in")
    # [{"type": "Group", "field": "activeUsers", "description": "Users... "
    #   "currently logged-in...", "field_type": "[User!]!", "score": 12.3}, ...]

The corpus is loaded lazily on the first call so that ``import rsc`` (and
the downstream ``from rubrik_security_cloud import RSC``) does not pay the
cost when a caller only needs the auth/client surface.
"""

from __future__ import annotations

import importlib.resources
import json
import re

_FIELDS_DATA: dict | None = None
_FIELDS_BM25: object | None = None  # rank_bm25.BM25Okapi once loaded

_CAMEL_RE = re.compile(r"[A-Z][a-z]+|[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+")

_QUERY_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "its", "of", "on", "or", "that", "the", "this", "to", "was",
    "were", "will", "with",
})


def _split_camel(s: str) -> list[str]:
    return [t.lower() for t in _CAMEL_RE.findall(s)]


# Lazy Snowball English (Porter2) stemmer -- mirrors mcp_indexer._stem so build
# and query tokenization stay symmetric. Initialized on first call to keep import
# of this module cheap (188µs baseline must not regress).
_stemmer = None


def _stem(token: str) -> str:
    global _stemmer
    if _stemmer is None:
        import snowballstemmer  # type: ignore

        _stemmer = snowballstemmer.stemmer("english")
    return _stemmer.stemWord(token)


def _load_fields_corpus() -> dict:
    global _FIELDS_DATA, _FIELDS_BM25
    if _FIELDS_DATA is None:
        from rank_bm25 import BM25Okapi  # type: ignore

        raw = (importlib.resources.files("rsc") / "mcp_fields_corpus.json").read_text()
        _FIELDS_DATA = json.loads(raw)
        _FIELDS_BM25 = BM25Okapi(_FIELDS_DATA["corpus"])
    return _FIELDS_DATA


_QUERY_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def _query_tokens(search: str) -> tuple[list[str], set[str]]:
    """Tokenize the user query.

    Returns ``(bm25_tokens, name_match_tokens)``. Stopwords are stripped from
    both because the corpus has them stripped too -- keeping them in the query
    would inflate scores for any document where a common word like "in" or
    "to" was dropped from the corpus but happened to appear in another row's
    raw text. ``name_match_tokens`` is the deduplicated set used to compute
    the name-token boost.
    """
    pieces: list[str] = []
    for raw in _QUERY_TOKEN_RE.findall(search.lower()):
        pieces.append(raw)
        pieces.extend(_split_camel(raw))
    deduped = list(dict.fromkeys(pieces))
    # Stem after stopword stripping so the stopword list stays in plain English.
    # Stemming applied symmetrically with the corpus build (mcp_indexer._stem_all).
    bm25_tokens = [_stem(t) for t in deduped if t and t not in _QUERY_STOPWORDS]
    name_match_tokens = set(bm25_tokens)
    return bm25_tokens, name_match_tokens


_NAME_TOKEN_BOOST = 1.5


def search_fields(
    search: str,
    limit: int = 10,
    include_deprecated: bool = True,
) -> list[dict]:
    """Search every field on every object/interface type by BM25 relevance.

    Useful when an operation-level search misses the semantic you care about
    because the relevant string lives on a nested field, not on the operation
    itself. Once you find the type/field, use :func:`describe_type` and
    :func:`search_operations` to trace which operations expose it.

    Tokenization mirrors :func:`rsc.search_operations`: camelCase splitting on
    type and field names so that ``activeUsers`` matches "active users" and
    ``lastLogin`` matches "login". Stopwords are stripped from both query and
    corpus to keep the BM25 IDF signal focused.

    Score is BM25 plus a small bonus per query token that exactly matches a
    camelCase token of the type or field name -- this surfaces fields whose
    names alone are diagnostic (e.g. ``User.lastLogin`` for "login") even when
    the description is sparse.

    Args:
        search: Natural-language query or keywords.
        limit: Maximum number of results (default 10).
        include_deprecated: Reserved for future use; deprecated fields are
            currently always returned because their docstrings still describe
            the canonical semantic.

    Returns:
        A list of dicts ranked by descending score. Each dict has keys:
        ``type``, ``field``, ``description``, ``field_type``, ``score``.
    """
    del include_deprecated  # accepted for API stability, not yet enforced

    data = _load_fields_corpus()
    assert _FIELDS_BM25 is not None  # set by _load_fields_corpus
    meta = data["meta"]

    bm25_tokens, name_tokens = _query_tokens(search)
    if not bm25_tokens:
        return []

    scores = _FIELDS_BM25.get_scores(bm25_tokens)

    results: list[tuple[int, float]] = []
    for i, base in enumerate(scores):
        if base <= 0:
            continue
        m = meta[i]
        # Name-token boost: count distinct query tokens that appear in the
        # stemmed camelCase split of the type or field name. Stemming both sides
        # keeps the comparison symmetric with the BM25 corpus.
        name_pool = {_stem(t) for t in (_split_camel(m["type"]) + _split_camel(m["field"]))}
        boost = _NAME_TOKEN_BOOST * len(name_tokens & name_pool)
        results.append((i, float(base) + boost))

    results.sort(key=lambda x: x[1], reverse=True)

    out: list[dict] = []
    for i, score in results[:limit]:
        m = meta[i]
        out.append({
            "type": m["type"],
            "field": m["field"],
            "description": m["description"] or None,
            "field_type": m["field_type"],
            "score": round(score, 4),
        })
    return out


def field_index_schema_version() -> str:
    """Return the YYYYMMDD schema version the field index was built from."""
    data = _load_fields_corpus()
    return data["schema_version"]
