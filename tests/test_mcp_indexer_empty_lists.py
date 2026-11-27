"""mcp_indexer on definitions with empty AST lists.

graphql-core 3.3 sets an empty list on an AST node (a field with no
arguments, for example) to None; earlier versions use an empty list.
The index must build with both.
"""

from rsc.mcp_indexer import build_operations_index, build_types_index

SDL = '''
type Query {
  "The deployed version."
  deploymentVersion: String!
  cluster(id: String!): Cluster
}

type Mutation {
  ping: Boolean
}

type Cluster {
  id: String!
}
'''


def test_operation_without_arguments():
    ops = build_operations_index(SDL)
    assert ops["queries"]["deploymentVersion"]["args"] == {}
    assert ops["queries"]["deploymentVersion"]["return_type"] == "String!"
    assert ops["queries"]["cluster"]["args"]["id"]["type"] == "String!"
    assert ops["mutations"]["ping"]["args"] == {}


def test_types_index_builds():
    types = build_types_index(SDL)
    assert types["Cluster"]["fields"]["id"]["type"] == "String!"
