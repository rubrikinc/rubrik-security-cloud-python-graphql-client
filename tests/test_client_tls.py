"""`RSCClient.endpoint` TLS wiring (the GraphQL path).

sgqlc's `HTTPEndpoint` talks to `urllib`, whose default context reads the
system/OpenSSL default trust store — a different, less predictable default
than `requests` (used for the token fetch in auth.py, see test_auth_tls.py),
which falls back to the certifi bundle automatically. That OS-default store
varies by Python distribution (e.g. Homebrew-linked vs. an un-initialized
python.org install), so `RSCClient.endpoint` always builds an explicit
`ssl.create_default_context(cafile=...)` and hands it to `HTTPEndpoint` via
its documented `urlopen` extension point (never by subclassing/
monkey-patching/mutating the global default context) — pinned to
`ca_cert_path` when set, or to the certifi bundle otherwise. Either way, the
trust anchor is deterministic and doesn't depend on which Python happened to
create the venv.

No network access: TokenManager.get_token is stubbed out.
"""
from unittest.mock import patch

from rsc.client import RSCClient
from rsc.config import Config


def _client(ca_cert_path=None):
    config = Config(url="https://rsc.example.com", client_id="id", client_secret="secret",
                     ca_cert_path=ca_cert_path)
    client = RSCClient(config=config)
    client._token_manager.get_token = lambda: "test-token"
    return client


def test_endpoint_uses_certifi_when_ca_cert_path_unset():
    import certifi

    client = _client()
    with patch("rsc.client.ssl.create_default_context") as mock_ctx, \
         patch("rsc.client.urllib.request.build_opener") as mock_build_opener:
        mock_build_opener.return_value.open = "sentinel-open"
        endpoint = client.endpoint

        mock_ctx.assert_called_once_with(cafile=certifi.where())
        assert mock_build_opener.called
        assert endpoint.urlopen == "sentinel-open"


def test_endpoint_passes_custom_opener_when_ca_cert_path_set(valid_pem):
    client = _client(ca_cert_path=valid_pem)
    with patch("rsc.client.ssl.create_default_context") as mock_ctx, \
         patch("rsc.client.urllib.request.build_opener") as mock_build_opener:
        mock_build_opener.return_value.open = "sentinel-open"
        endpoint = client.endpoint

        # ca_cert_path takes precedence over the certifi default.
        mock_ctx.assert_called_once_with(cafile=valid_pem)
        assert mock_build_opener.called
        assert endpoint.urlopen == "sentinel-open"


def test_endpoint_url_and_headers_unaffected_by_ca_cert_path(tmp_path):
    client = _client()
    endpoint = client.endpoint
    assert endpoint.url == "https://rsc.example.com/api/graphql"
    assert endpoint.base_headers["Authorization"] == "Bearer test-token"
