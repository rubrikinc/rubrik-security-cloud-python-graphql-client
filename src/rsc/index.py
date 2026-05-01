"""
Discovery functions for RSC GraphQL operations and types.

The index is pre-generated from the GraphQL SDL and shipped with the package,
so these functions work without any credentials or network access.

Example usage (e.g. from an MCP server):

    from rsc import search_operations, describe_operation, describe_type

    # Find relevant queries
    results = search_operations("snapshot", "query")

    # Get full argument signature
    op = describe_operation("vSphereVmNewConnection", "query")

    # Look up an input type's fields
    t = describe_type("CreateGlobalSlaInput")
"""

from __future__ import annotations

import importlib.resources
import json
import re

_ops_index: dict | None = None
_types_index: dict | None = None
_bm25_index: object | None = None  # rank_bm25.BM25Okapi once loaded
_bm25_meta: list[dict] | None = None

_CAMEL_RE = re.compile(r"[A-Z][a-z]+|[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+")


def _split_camel(s: str) -> list[str]:
    return [t.lower() for t in _CAMEL_RE.findall(s)]


def _get_ops() -> dict:
    global _ops_index
    if _ops_index is None:
        data = (importlib.resources.files("rsc") / "mcp_index.json").read_text()
        _ops_index = json.loads(data)
    return _ops_index


def _get_types() -> dict:
    global _types_index
    if _types_index is None:
        data = (importlib.resources.files("rsc") / "mcp_types.json").read_text()
        _types_index = json.loads(data)
    return _types_index


def _get_bm25():
    global _bm25_index, _bm25_meta
    if _bm25_index is None:
        from rank_bm25 import BM25Okapi  # type: ignore

        data = json.loads((importlib.resources.files("rsc") / "mcp_bm25_corpus.json").read_text())
        _bm25_meta = data["meta"]
        _bm25_index = BM25Okapi(data["corpus"])
    return _bm25_index, _bm25_meta


def search_operations(search: str, operation_type: str = "all") -> list[dict]:
    """Search queries and/or mutations by BM25 relevance with camelCase tokenization.

    Finds operations by name, description, and return-type field names. CamelCase
    splitting means "compliance" matches operations whose return types contain fields
    like ``complianceStatus`` or ``protectionStatus``.

    Args:
        search: Natural-language query or keywords.
        operation_type: One of "query", "mutation", or "all" (default).

    Returns:
        List of dicts with keys: name, type, description, return_type, score.
    """
    index, meta = _get_bm25()
    query_tokens = _split_camel(search) + search.lower().split()
    scores = index.get_scores(query_tokens)

    candidates = [
        (i, float(scores[i]))
        for i, m in enumerate(meta)
        if operation_type == "all" or m["type"] == operation_type
    ]
    candidates.sort(key=lambda x: x[1], reverse=True)

    results = []
    for i, score in candidates[:10]:
        if score <= 0:
            break
        m = meta[i]
        results.append({
            "name": m["name"],
            "type": m["type"],
            "description": m["description"],
            "return_type": m["return_type"],
            "score": round(score, 4),
        })
    return results


def describe_operation(name: str, operation_type: str) -> dict:
    """Return the full signature for a query or mutation.

    Args:
        name: camelCase operation name (e.g. "vSphereVmNewConnection").
        operation_type: "query" or "mutation".

    Returns:
        Dict with keys: name, type, description, return_type,
        args (dict of argName -> {type, description}).

    Raises:
        ValueError: If the operation is not found.
    """
    ops = _get_ops()
    pool = ops["queries"] if operation_type == "query" else ops["mutations"]
    if name not in pool:
        raise ValueError(
            f"{operation_type} '{name}' not found. "
            "Use search_operations() to find available operations."
        )
    return {"name": name, "type": operation_type, **pool[name]}


def describe_type(name: str) -> dict:
    """Return the fields or values for a GraphQL type.

    Args:
        name: Type name (e.g. "CreateGlobalSlaInput", "SlaAssignTypeEnum").

    Returns:
        Dict with keys: name, kind ("input"|"type"|"enum"|"interface"|"union"),
        and either fields (dict of fieldName -> {type, description})
        or values (list of strings for enums)
        or types (list of strings for unions).

    Raises:
        ValueError: If the type is not found.
    """
    types = _get_types()
    if name not in types:
        raise ValueError(
            f"Type '{name}' not found. Use list_types() to see available types."
        )
    return {"name": name, **types[name]}


def list_queries() -> list[str]:
    """Return all query names (camelCase)."""
    return list(_get_ops()["queries"].keys())


def list_mutations() -> list[str]:
    """Return all mutation names (camelCase)."""
    return list(_get_ops()["mutations"].keys())


def list_types() -> list[str]:
    """Return all type names."""
    return list(_get_types().keys())
