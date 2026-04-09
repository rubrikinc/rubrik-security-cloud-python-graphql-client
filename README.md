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

## Token caching

Tokens are cached in `~/.rsc/token_cache_<hash>.json` (`0600` permissions) and reused until 60 seconds before expiry. Short-lived callers like cron jobs or Telegraf scripts won't re-authenticate on every run. Cache files are keyed by a hash of the RSC URL so multiple accounts on the same machine stay isolated.
