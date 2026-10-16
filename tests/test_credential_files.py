"""Credential file loading for service accounts and personal access tokens.

Both file types share the same shape (client_id, client_secret,
access_token_uri) but point at different token endpoints. The base URL must
come from the token URI's origin, and the token cache must be keyed per
credential so two identities on one tenant never share a cached token.

No network access.
"""
import json

from rsc.auth import TokenManager
from rsc.config import Config, load_config_from_service_account


def _write_cred_file(tmp_path, token_uri, client_id="id"):
    path = tmp_path / "cred.json"
    path.write_text(json.dumps({
        "client_id": client_id,
        "client_secret": "secret",
        "access_token_uri": token_uri,
    }))
    return str(path)


def test_service_account_file_base_url_and_token_uri(tmp_path):
    cfg = load_config_from_service_account(
        _write_cred_file(tmp_path, "https://rsc.example.com/api/client_token"))
    assert cfg.url == "https://rsc.example.com"
    assert cfg.token_uri == "https://rsc.example.com/api/client_token"


def test_pat_file_base_url_and_token_uri(tmp_path):
    cfg = load_config_from_service_account(
        _write_cred_file(tmp_path, "https://rsc.example.com/api/pat_login"))
    assert cfg.url == "https://rsc.example.com"
    assert cfg.token_uri == "https://rsc.example.com/api/pat_login"


def test_token_cache_is_separate_per_client_id(tmp_path, monkeypatch):
    monkeypatch.setattr("rsc.auth.Path.home", staticmethod(lambda: tmp_path))
    sa = TokenManager(Config(url="https://rsc.example.com", client_id="sa-id", client_secret="s"))
    pat = TokenManager(Config(url="https://rsc.example.com", client_id="pat-id", client_secret="s"))
    assert sa._cache_file != pat._cache_file


def test_pat_login_403_raises_feature_not_enabled(tmp_path, monkeypatch):
    from unittest.mock import MagicMock, patch

    import pytest

    monkeypatch.setattr("rsc.auth.Path.home", staticmethod(lambda: tmp_path))
    manager = TokenManager(Config(url="https://rsc.example.com", client_id="id", client_secret="s",
                                  token_uri="https://rsc.example.com/api/pat_login"))
    resp = MagicMock(status_code=403, text="Personal Access Token feature has not been enabled on RSC.")
    with patch("rsc.auth.requests.post", return_value=resp):
        with pytest.raises(PermissionError, match="not be enabled"):
            manager._fetch_token()


def test_pat_file_fetch_token_posts_to_pat_login(tmp_path, monkeypatch):
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr("rsc.auth.Path.home", staticmethod(lambda: tmp_path))
    cfg = load_config_from_service_account(
        _write_cred_file(tmp_path, "https://rsc.example.com/api/pat_login"))
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"access_token": "tok", "expires_in": 43200}
    with patch("rsc.auth.requests.post", return_value=resp) as mock_post:
        assert TokenManager(cfg)._fetch_token() == "tok"
    assert mock_post.call_args.args[0] == "https://rsc.example.com/api/pat_login"


def test_pat_login_403_matches_trailing_slash_and_chains_http_error(tmp_path, monkeypatch):
    from unittest.mock import MagicMock, patch

    import pytest
    import requests

    monkeypatch.setattr("rsc.auth.Path.home", staticmethod(lambda: tmp_path))
    manager = TokenManager(Config(url="https://rsc.example.com", client_id="id", client_secret="s",
                                  token_uri="https://rsc.example.com/api/pat_login/"))
    resp = MagicMock(status_code=403, text="Personal Access Token feature has not been enabled on RSC.")
    with patch("rsc.auth.requests.post", return_value=resp):
        with pytest.raises(PermissionError) as exc_info:
            manager._fetch_token()
    assert isinstance(exc_info.value.__cause__, requests.HTTPError)
    assert exc_info.value.__cause__.response is resp
