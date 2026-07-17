import sys

from sgqlc.endpoint.http import HTTPEndpoint

from ._version import _sdk_headers
from .auth import TokenManager
from .config import Config, load_config, load_config_from_service_account

_LARGE_RESULT_THRESHOLD = 1000


class RSCClient:
    def __init__(self, config: Config = None, service_account_file=None,
                 product: str = None, product_version: str = None):
        if config is not None:
            self._config = config
        elif service_account_file is not None:
            self._config = load_config_from_service_account(service_account_file)
        else:
            self._config = load_config()
        self._token_manager = TokenManager(self._config)
        self._product = product
        self._product_version = product_version

    @property
    def endpoint(self) -> HTTPEndpoint:
        token = self._token_manager.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        headers.update(_sdk_headers(self._product, self._product_version))
        return HTTPEndpoint(
            f"{self._config.url}/api/graphql",
            headers,
            timeout=30,
        )

    def execute(self, operation, variables: dict = None, max_records: int = None):
        variables = dict(variables or {})
        result = self.endpoint(operation, variables=variables)

        data = result.get("data") or {}
        conn_key = next(
            (k for k, v in data.items() if isinstance(v, dict) and "nodes" in v and "pageInfo" in v),
            None,
        )

        result.pop("headers", None)

        if conn_key is None:
            # Truncation guard. Responses paginate two ways: `nodes` + `pageInfo`
            # (auto-paginated below), or a `data` list plus `hasMore` / `nextCursor`
            # (not auto-paginated). In either case, if this single response is not
            # the full set, warn so a first page isn't mistaken for everything.
            for key, val in data.items():
                if not isinstance(val, dict):
                    continue
                items = (
                    val.get("nodes") if isinstance(val.get("nodes"), list)
                    else val.get("data") if isinstance(val.get("data"), list)
                    else None
                )
                if items is None:
                    continue
                total = (
                    val.get("count") if isinstance(val.get("count"), int)
                    else val.get("total") if isinstance(val.get("total"), int)
                    else None
                )
                # Trust `hasMore` when present; fall back to a non-empty
                # `nextCursor` only when `hasMore` is absent (a populated cursor
                # on a final page shouldn't read as "more available").
                flag = val.get("hasMore")
                has_more = flag is True or (flag is None and bool(val.get("nextCursor")))
                if (total is not None and total > len(items)) or has_more:
                    shown = f"{len(items)} of {total}" if total is not None else str(len(items))
                    print(
                        f"Warning: '{key}' returned {shown} records (first page only). "
                        "More results are available — paginate to retrieve the rest "
                        "(cursor connections: add `pageInfo` + `$after`/`after: $after`; "
                        "`hasMore`/`nextCursor` responses: re-request with the returned "
                        "`nextCursor`).",
                        file=sys.stderr,
                    )
            return result

        conn = data[conn_key]
        total = conn.get("count")

        if total and total > _LARGE_RESULT_THRESHOLD:
            limit = f", fetching first {max_records:,}" if max_records else ""
            print(f"Note: {total:,} records found{limit}. This may take a while...", file=sys.stderr)

        all_nodes = list(conn["nodes"])

        while conn["pageInfo"]["hasNextPage"]:
            if max_records and len(all_nodes) >= max_records:
                break
            after = conn["pageInfo"]["endCursor"]
            variables["after"] = after
            conn = self.endpoint(operation, variables=variables)["data"][conn_key]
            # Guard against a non-advancing cursor. If the operation does not
            # declare `$after` and pass `after: $after` to the connection, the
            # injected cursor is ignored and the server returns the same page
            # (same endCursor) with hasNextPage=true — an infinite loop on page 1.
            # Detect the repeated cursor and stop rather than loop forever.
            if conn["pageInfo"]["endCursor"] == after:
                print(
                    "Warning: pagination cursor did not advance; returning results "
                    "gathered so far. The operation likely omits `after: $after` — "
                    "add `$after: String` to the operation and pass `after: $after` "
                    "to the connection field to paginate.",
                    file=sys.stderr,
                )
                break
            all_nodes.extend(conn["nodes"])

        result["data"][conn_key]["nodes"] = all_nodes[:max_records] if max_records else all_nodes
        return result
