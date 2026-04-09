"""
Builds mcp_index.json and mcp_types.json from the latest SDL in schemas/.

These files are committed into src/rsc/ and shipped in the package wheel so
that the index functions in index.py work without any runtime SDL parsing.

Run manually:
    python -m rsc.mcp_indexer

This script is also invoked by the CI schema-update workflow after generating
schema.py, so the index always stays in sync with the latest schema.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from graphql import parse as gql_parse
from graphql.language.ast import ListTypeNode, NonNullTypeNode


def _type_to_str(node) -> str:
    if isinstance(node, NonNullTypeNode):
        return _type_to_str(node.type) + "!"
    if isinstance(node, ListTypeNode):
        return "[" + _type_to_str(node.type) + "]"
    return node.name.value


def _extract_comment(sdl: str, loc_start: int) -> str | None:
    """Extract the # comment block immediately preceding a field definition."""
    before = sdl[:loc_start]
    lines = before.split("\n")
    comment_lines = []
    i = len(lines) - 1
    # Skip blank lines between comment and field
    while i >= 0 and not lines[i].strip():
        i -= 1
    # Collect consecutive # lines
    while i >= 0 and lines[i].strip().startswith("#"):
        comment_lines.insert(0, lines[i].strip()[1:].lstrip())
        i -= 1
    return " ".join(comment_lines).strip() or None


def build_operations_index(sdl: str) -> dict:
    doc = gql_parse(sdl)
    index: dict = {"queries": {}, "mutations": {}}
    for defn in doc.definitions:
        if not (hasattr(defn, "name") and defn.name and defn.name.value in ("Query", "Mutation")):
            continue
        category = "queries" if defn.name.value == "Query" else "mutations"
        for field in defn.fields:
            args = {}
            for arg in field.arguments:
                args[arg.name.value] = {
                    "type": _type_to_str(arg.type),
                    "description": _extract_comment(sdl, arg.loc.start),
                }
            index[category][field.name.value] = {
                "description": _extract_comment(sdl, field.loc.start),
                "return_type": _type_to_str(field.type),
                "args": args,
            }
    return index


def build_types_index(sdl: str) -> dict:
    doc = gql_parse(sdl)
    types: dict = {}
    kind_map = {
        "InputObjectTypeDefinitionNode": "input",
        "ObjectTypeDefinitionNode": "type",
        "EnumTypeDefinitionNode": "enum",
        "InterfaceTypeDefinitionNode": "interface",
        "UnionTypeDefinitionNode": "union",
    }
    for defn in doc.definitions:
        kind = kind_map.get(type(defn).__name__)
        if not kind or not hasattr(defn, "name") or not defn.name:
            continue
        name = defn.name.value
        if name in ("Query", "Mutation"):
            continue
        if kind == "enum":
            types[name] = {"kind": kind, "values": [v.name.value for v in defn.values]}
        elif kind == "union":
            types[name] = {"kind": kind, "types": [t.name.value for t in defn.types]}
        else:
            fields = {}
            for f in defn.fields:
                fields[f.name.value] = {
                    "type": _type_to_str(f.type),
                    "description": _extract_comment(sdl, f.loc.start),
                }
            types[name] = {"kind": kind, "fields": fields}
    return types


def find_latest_sdl(schemas_dir: Path) -> Path:
    files = sorted(schemas_dir.glob("*.graphql"))
    if not files:
        raise FileNotFoundError(f"No .graphql files found in {schemas_dir}")
    return files[-1]


def main() -> None:
    repo_root = Path(__file__).parent.parent.parent
    schemas_dir = repo_root / "schemas"
    out_dir = Path(__file__).parent

    sdl_file = find_latest_sdl(schemas_dir)
    print(f"Building index from {sdl_file.name}...", flush=True)
    sdl = sdl_file.read_text()

    print("  Parsing operations...", flush=True)
    ops = build_operations_index(sdl)
    ops_path = out_dir / "mcp_index.json"
    ops_path.write_text(json.dumps(ops, separators=(",", ":")))
    q = len(ops["queries"])
    m = len(ops["mutations"])
    print(f"  mcp_index.json: {q} queries, {m} mutations ({ops_path.stat().st_size // 1024}KB)")

    print("  Parsing types...", flush=True)
    types = build_types_index(sdl)
    types_path = out_dir / "mcp_types.json"
    types_path.write_text(json.dumps(types, separators=(",", ":")))
    print(f"  mcp_types.json: {len(types)} types ({types_path.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
