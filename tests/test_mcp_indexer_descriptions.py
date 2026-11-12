"""Description extraction in mcp_indexer for both schema description formats.

Schemas through 20261026 carry descriptions as # comments. From 20261102 on
they carry GraphQL string descriptions. The index must read both.
"""

from rsc.mcp_indexer import build_operations_index, build_types_index

COMMENT_SDL = '''
type Query {
  # Look up a cluster.
  cluster(
    # Cluster ID.
    id: String!
  ): Cluster
}

type Cluster {
  # Cluster name.
  name: String
}
'''

STRING_SDL = '''
type Query {
  "Look up a cluster."
  cluster(
    "Cluster ID."
    id: String!
  ): Cluster
}

type Cluster {
  """
  Cluster
  name.
  """
  name: String
}
'''

NO_DESCRIPTION_SDL = '''
type Query {
  cluster(id: String!): Cluster
}

type Cluster {
  name: String
}
'''


def _descriptions(sdl):
    op = build_operations_index(sdl)["queries"]["cluster"]
    field = build_types_index(sdl)["Cluster"]["fields"]["name"]
    return op["description"], op["args"]["id"]["description"], field["description"]


def test_hash_comment_descriptions():
    assert _descriptions(COMMENT_SDL) == ("Look up a cluster.", "Cluster ID.", "Cluster name.")


def test_string_descriptions():
    # Block strings are collapsed to one line, the same as # comment blocks.
    assert _descriptions(STRING_SDL) == ("Look up a cluster.", "Cluster ID.", "Cluster name.")


def test_missing_descriptions_are_none():
    assert _descriptions(NO_DESCRIPTION_SDL) == (None, None, None)
