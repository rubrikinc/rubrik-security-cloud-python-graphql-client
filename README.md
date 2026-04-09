# rubrik-security-cloud-python-graphql-client

Python client for the Rubrik Security Cloud (RSC) GraphQL API. Provides authenticated GraphQL execution via [sgqlc](https://github.com/profusion/sgqlc), with OAuth2 token management and a generated typed schema so you never have to write raw GraphQL strings.

## Installation

```bash
pip install rsc-client
```

To install directly from this repo:

```bash
pip install git+https://github.com/rubrikinc/rubrik-security-cloud-python-graphql-client.git
```

## Authentication

### Service account file (recommended)

Download a service account JSON file from the RSC UI (**Access Control → Service Accounts**) and pass it to the client:

```python
from rsc import RSCClient

client = RSCClient(service_account_file="~/Downloads/my-service-account.json")
```

Or set an environment variable and call `RSCClient()` with no arguments:

```bash
export RSC_SERVICE_ACCOUNT_FILE=~/Downloads/my-service-account.json
```

### `~/.rsc/config.json`

```json
{
  "url": "https://myaccount.my.rubrik.com",
  "client_id": "client|...",
  "client_secret": "..."
}
```

You can also point this file at a service account file:

```json
{
  "service_account_file": "/path/to/service-account.json"
}
```

### Environment variables

| Variable | Description |
|---|---|
| `RSC_SERVICE_ACCOUNT_FILE` | Path to a service account JSON file |
| `RSC_URL` | RSC base URL |
| `RSC_CLIENT_ID` | OAuth2 client ID |
| `RSC_CLIENT_SECRET` | OAuth2 client secret |

**Precedence:** `RSC_SERVICE_ACCOUNT_FILE` → `RSC_URL`/`RSC_CLIENT_ID`/`RSC_CLIENT_SECRET` → `~/.rsc/config.json`

---

## Usage

`RSCClient.execute()` accepts either a raw GraphQL string or an sgqlc `Operation`. The sgqlc approach is recommended — it gives you typed, auto-completed Python objects and catches field name errors before the request is sent.

### Query example — list SLA domains

<table>
<tr><th>Raw GraphQL string</th><th>sgqlc Operation</th></tr>
<tr>
<td>

```python
result = client.execute("""
  query {
    slaDomains {
      nodes {
        id
        name
      }
    }
  }
""")

for node in result['data']['slaDomains']['nodes']:
    print(node['id'], node['name'])
```

</td>
<td>

```python
from sgqlc.operation import Operation
from rsc.schema import Query

op = Operation(Query)
nodes = op.sla_domains().nodes()
nodes.__fields__('id', 'name')

result = client.execute(op)

# Deserialize into typed objects
data = (op + result).sla_domains
for node in data.nodes:
    print(node.id, node.name)
```

</td>
</tr>
</table>

### Mutation example — assign an SLA domain

<table>
<tr><th>Raw GraphQL string</th><th>sgqlc Operation</th></tr>
<tr>
<td>

```python
result = client.execute("""
  mutation {
    assignSla(input: {
      objectIds: ["<object-id>"],
      slaDomainAssignType: PROTECT,
      slaOptionalId: "<sla-id>"
    }) {
      success
    }
  }
""")

print(result['data']['assignSla']['success'])
```

</td>
<td>

```python
from sgqlc.operation import Operation
from rsc.schema import Mutation, AssignSlaInput, SlaAssignTypeEnum

op = Operation(Mutation)
result_field = op.assign_sla(input=AssignSlaInput(
    object_ids=["<object-id>"],
    sla_domain_assign_type=SlaAssignTypeEnum.PROTECT,
    sla_optional_id="<sla-id>",
))
result_field.__fields__('success')

result = client.execute(op)

data = (op + result).assign_sla
print(data.success)
```

</td>
</tr>
</table>

---

## Discovery index

The package ships two pre-generated JSON indexes built from the GraphQL SDL: `mcp_index.json` (all queries and mutations with their argument signatures) and `mcp_types.json` (all named types with their fields, enum values, or union members). These are parsed once at import time and cached in memory.

### Why it exists

A common mistake when building an MCP server for a GraphQL API is to create one MCP tool per operation — a pattern that produces thousands of redundant tools and defeats the purpose of both technologies. GraphQL was designed so that a single endpoint can express any query or mutation; MCP tools should reflect that by exposing a small, generic surface: one tool to search operations, one to describe an operation, one to execute it. The LLM then does what it's good at — using those tools to discover and compose the right call at runtime.

The discovery index makes this practical. The RSC schema is large, and an LLM needs a fast way to answer "what operations exist and how do I call them?" without parsing the raw SDL on every request. The indexes are pre-built by CI whenever the schema changes and committed into the package, so discovery works instantly with no credentials, no network access, and no heavy runtime dependencies.

### Functions

```python
from rsc import (
    search_operations,   # full-text search across names + descriptions
    describe_operation,  # full argument signature for one operation
    describe_type,       # fields/values for any named type
    list_queries,        # all query names
    list_mutations,      # all mutation names
    list_types,          # all type names
)
```

#### `search_operations(search, operation_type="all")`

Case-insensitive substring search across operation names and descriptions. Useful for finding the right operation when you know roughly what you're looking for.

```python
search_operations("snapshot", "query")
# [{"name": "...", "type": "query", "description": "...", "return_type": "..."}, ...]

search_operations("assign", "mutation")
```

#### `describe_operation(name, operation_type)`

Returns the full argument signature for a single query or mutation. Operation names are camelCase as they appear in GraphQL (e.g. `vSphereVmNewConnection`).

```python
op = describe_operation("slaDomains", "query")
# {
#   "name": "slaDomains",
#   "type": "query",
#   "description": "...",
#   "return_type": "SlaDomainConnection",
#   "args": {
#     "filter": {"type": "[Filter!]", "description": "..."},
#     ...
#   }
# }
```

#### `describe_type(name)`

Returns the fields (with types and descriptions) for object/input/interface types, the possible values for enums, or the member types for unions.

```python
describe_type("CreateGlobalSlaInput")
# {"name": "CreateGlobalSlaInput", "kind": "input", "fields": {"name": {"type": "String!", ...}, ...}}

describe_type("SlaAssignTypeEnum")
# {"name": "SlaAssignTypeEnum", "kind": "enum", "values": ["PROTECT", "UNPROTECT", ...]}
```

### Keeping the index in sync

The indexes are regenerated automatically by the CI workflow whenever a new schema file is added. To regenerate locally after adding a schema or modifying `mcp_indexer.py`:

```bash
PYTHONPATH=src python3 -m rsc.mcp_indexer
```

Then commit the updated `mcp_index.json` and `mcp_types.json`.

---

## Token caching

Tokens are cached in `~/.rsc/token_cache_<hash>.json` (`0600` permissions) and reused until 60 seconds before expiry. Short-lived callers like cron jobs or Telegraf scripts won't re-authenticate on every run. Cache files are keyed by a hash of the RSC URL so multiple accounts on the same machine stay isolated.
