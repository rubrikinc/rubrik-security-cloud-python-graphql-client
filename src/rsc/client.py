from sgqlc.endpoint.http import HTTPEndpoint

from ._version import _user_agent
from .auth import TokenManager
from .config import Config, load_config, load_config_from_service_account


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

    def execute(self, operation, variables: dict = None):
        return self.endpoint(operation, variables=variables)
