import sys

from sgqlc.endpoint.http import HTTPEndpoint

from ._version import _user_agent
from .auth import TokenManager
from .config import Config, load_config, load_config_from_service_account

_LARGE_RESULT_THRESHOLD = 1000


class RSCClient:
    def __init__(self, config: Config = None, service_account_file=None):
        if config is not None:
            self._config = config
        elif service_account_file is not None:
            self._config = load_config_from_service_account(service_account_file)
        else:
            self._config = load_config()
        self._token_manager = TokenManager(self._config)

    @property
    def endpoint(self) -> HTTPEndpoint:
        token = self._token_manager.get_token()
        return HTTPEndpoint(
            f"{self._config.url}/api/graphql",
            {
                "Authorization": f"Bearer {token}",
                "User-Agent": _user_agent(),
            },
        )

    def execute(self, operation, variables: dict = None, max_records: int = None):
        variables = dict(variables or {})
        result = self.endpoint(operation, variables=variables)

        data = result.get("data") or {}
        conn_key = next(
            (k for k, v in data.items() if isinstance(v, dict) and "nodes" in v and "pageInfo" in v),
            None,
        )

        if conn_key is None:
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
            variables["after"] = conn["pageInfo"]["endCursor"]
            conn = self.endpoint(operation, variables=variables)["data"][conn_key]
            all_nodes.extend(conn["nodes"])

        result["data"][conn_key]["nodes"] = all_nodes[:max_records] if max_records else all_nodes
        return result
