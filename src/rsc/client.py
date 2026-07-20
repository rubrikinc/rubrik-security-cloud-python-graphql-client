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
        result.pop("headers", None)

        conn_key = next(
            (k for k, v in data.items() if isinstance(v, dict) and "nodes" in v and "pageInfo" in v),
            None,
        )

        if conn_key is not None:
            conn = data[conn_key]
            total = conn.get("count")

            if total and total > _LARGE_RESULT_THRESHOLD:
                limit = f", fetching first {max_records:,}" if max_records is not None else ""
                print(f"Note: {total:,} records found{limit}. This may take a while...", file=sys.stderr)

            all_nodes = list(conn["nodes"])

            while conn["pageInfo"]["hasNextPage"]:
                if max_records is not None and len(all_nodes) >= max_records:
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

            if max_records is not None:
                all_nodes = all_nodes[:max_records]
            result["data"][conn_key]["nodes"] = all_nodes
            # Keep pageInfo accurate on the returned connection: reflect the last
            # fetched page so a caller can detect an incomplete result (e.g. we
            # stopped at max_records, or the cursor guard fired) from the return
            # value alone — the stderr warning isn't visible to every consumer.
            result["data"][conn_key]["pageInfo"] = conn["pageInfo"]

        # Truncation scan over ALL top-level fields — including a second
        # connection that was not auto-paginated, or a `data`/`hasMore` field
        # returned alongside the auto-paginated connection. Warn so a first page
        # isn't mistaken for the whole set. Skips the auto-paginated field, whose
        # (now-accurate) pageInfo is the truncation signal for that one.
        self._warn_if_truncated(data, skip_key=conn_key)
        return result

    @staticmethod
    def _has_more(val):
        """Best-effort 'more results available' from a `data`/`hasMore` field.

        Trusts `hasMore` when present (accepting bool or the string forms some
        endpoints emit); only when it's absent does a populated `nextCursor`
        imply more (a cursor on a final page shouldn't read as "more available").
        """
        flag = val.get("hasMore")
        if isinstance(flag, bool):
            return flag
        if isinstance(flag, str):
            return flag.strip().lower() == "true"
        return bool(val.get("nextCursor"))

    def _warn_if_truncated(self, data, skip_key=None):
        for key, val in data.items():
            if key == skip_key or not isinstance(val, dict):
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
            page_info = val.get("pageInfo")
            relay_more = isinstance(page_info, dict) and bool(page_info.get("hasNextPage"))
            if (total is not None and total > len(items)) or relay_more or self._has_more(val):
                shown = f"{len(items)} of {total}" if total is not None else str(len(items))
                print(
                    f"Warning: '{key}' returned {shown} records (first page only). "
                    "More results are available — paginate to retrieve the rest "
                    "(cursor connections: add `pageInfo` + `$after`/`after: $after`; "
                    "`hasMore`/`nextCursor` responses: re-request with the returned "
                    "`nextCursor`).",
                    file=sys.stderr,
                )
