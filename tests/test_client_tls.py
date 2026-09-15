"""`RSCClient.endpoint` TLS wiring (the GraphQL path).

sgqlc's `HTTPEndpoint` talks to `urllib`, whose default context reads the
system/OpenSSL trust store — a different default than `requests` (used for
the token fetch in auth.py, see test_auth_tls.py). When `ca_cert_path` is
set, `RSCClient.endpoint` must build an `ssl.create_default_context(cafile=...)`
and hand it to `HTTPEndpoint` via its documented `urlopen` extension point
(never by subclassing/monkey-patching/mutating the global default context).
When unset, behavior must be unchanged (HTTPEndpoint's own default urlopen).

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


def test_endpoint_uses_default_urlopen_when_ca_cert_path_unset():
    client = _client()
    endpoint = client.endpoint
    # HTTPEndpoint falls back to urllib.request.urlopen when urlopen=None is
    # passed through, reproducing today's behavior exactly.
    import urllib.request
    assert endpoint.urlopen is urllib.request.urlopen


def test_endpoint_passes_custom_opener_when_ca_cert_path_set(valid_pem):
    client = _client(ca_cert_path=valid_pem)
    with patch("rsc.client.ssl.create_default_context") as mock_ctx, \
         patch("rsc.client.urllib.request.build_opener") as mock_build_opener:
        mock_build_opener.return_value.open = "sentinel-open"
        endpoint = client.endpoint

        mock_ctx.assert_called_once_with(cafile=valid_pem)
        assert mock_build_opener.called
        assert endpoint.urlopen == "sentinel-open"


def test_endpoint_url_and_headers_unaffected_by_ca_cert_path(tmp_path):
    client = _client()
    endpoint = client.endpoint
    assert endpoint.url == "https://rsc.example.com/api/graphql"
    assert endpoint.base_headers["Authorization"] == "Bearer test-token"
