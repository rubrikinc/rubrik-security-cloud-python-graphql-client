"""TokenManager._fetch_token TLS wiring (the OAuth token path).

`requests` does not consult `SSL_CERT_FILE` (the variable urllib's default
context reads) at all — only `REQUESTS_CA_BUNDLE` / `CURL_CA_BUNDLE`, or an
explicit `verify=` kwarg. So `ca_cert_path` must reach `requests.post` via
`verify=` explicitly; when unset, `verify=True` must reproduce today's
behavior exactly (validate against the certifi bundle).

No network access: requests.post is mocked.
"""
from unittest.mock import MagicMock, patch

from rsc.auth import TokenManager
from rsc.config import Config


def _manager(tmp_path, ca_cert_path=None, monkeypatch=None):
    config = Config(url="https://rsc.example.com", client_id="id", client_secret="secret",
                     ca_cert_path=ca_cert_path)
    if monkeypatch is not None:
        monkeypatch.setattr("rsc.auth.Path.home", staticmethod(lambda: tmp_path))
    return TokenManager(config)


def _mock_response():
    resp = MagicMock()
    resp.json.return_value = {"access_token": "tok", "expires_in": 3600}
    resp.raise_for_status.return_value = None
    return resp


def test_fetch_token_passes_verify_true_when_ca_cert_path_unset(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch=monkeypatch)
    with patch("rsc.auth.requests.post", return_value=_mock_response()) as mock_post:
        manager._fetch_token()
    assert mock_post.call_args.kwargs["verify"] is True


def test_fetch_token_passes_ca_cert_path_as_verify_when_set(tmp_path, monkeypatch, valid_pem):
    manager = _manager(tmp_path, ca_cert_path=valid_pem, monkeypatch=monkeypatch)
    with patch("rsc.auth.requests.post", return_value=_mock_response()) as mock_post:
        manager._fetch_token()
    assert mock_post.call_args.kwargs["verify"] == valid_pem


def test_fetch_token_still_returns_token(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch=monkeypatch)
    with patch("rsc.auth.requests.post", return_value=_mock_response()):
        token = manager._fetch_token()
    assert token == "tok"
