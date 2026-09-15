"""`ca_cert_path` config plumbing — `RSC_CA_CERT_FILE` only.

Deliberately env-var-only: one documented way to configure the trust anchor,
rather than three places a customer could set it and support would have to
check. It is read on both config paths, including the service-account one,
which `load_config()` hands off to and returns from.

- read from the env var on every config path,
- eager validation at config load (missing file, unreadable file, non-PEM
  content) rather than a deferred handshake error,
- unset behavior is unchanged,
- the rotation warning fires once per process, not once per Config.

No network access; a self-signed certificate is generated at test time so
nothing sensitive is committed to this public repo.
"""
import pytest

import rsc.config as config_module
from rsc.config import Config, load_config, load_config_from_service_account


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    # Every test starts with a clean env and a reset "warned once" flag so
    # tests don't leak state into each other.
    for var in ("RSC_URL", "RSC_CLIENT_ID", "RSC_CLIENT_SECRET", "RSC_CA_CERT_FILE",
                "RSC_SERVICE_ACCOUNT_FILE", "RSC_INSECURE_HTTP"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(config_module, "_warned_self_signed_cert", False)
    yield


# --------------------------------------------------------------------------- #
# unset behavior unchanged
# --------------------------------------------------------------------------- #

def test_ca_cert_path_defaults_to_none():
    cfg = Config(url="https://rsc.example.com", client_id="id", client_secret="secret")
    assert cfg.ca_cert_path is None


def test_load_config_without_ca_cert_env_leaves_it_unset(monkeypatch):
    monkeypatch.setenv("RSC_URL", "https://rsc.example.com")
    monkeypatch.setenv("RSC_CLIENT_ID", "id")
    monkeypatch.setenv("RSC_CLIENT_SECRET", "secret")
    cfg = load_config()
    assert cfg.ca_cert_path is None


# --------------------------------------------------------------------------- #
# precedence
# --------------------------------------------------------------------------- #

def test_ca_cert_path_read_from_env_var(monkeypatch, valid_pem):
    monkeypatch.setenv("RSC_URL", "https://rsc.example.com")
    monkeypatch.setenv("RSC_CLIENT_ID", "id")
    monkeypatch.setenv("RSC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("RSC_CA_CERT_FILE", valid_pem)
    cfg = load_config()
    assert cfg.ca_cert_path == valid_pem


def test_ca_cert_path_from_service_account_env_var(monkeypatch, tmp_path, valid_pem):
    sa_file = tmp_path / "sa.json"
    sa_file.write_text(
        '{"client_id": "id", "client_secret": "secret", '
        '"access_token_uri": "https://rsc.example.com/api/client_token"}'
    )
    monkeypatch.setenv("RSC_CA_CERT_FILE", valid_pem)
    cfg = load_config_from_service_account(str(sa_file))
    assert cfg.ca_cert_path == valid_pem
    assert cfg.url == "https://rsc.example.com"


# --------------------------------------------------------------------------- #
# eager validation
# --------------------------------------------------------------------------- #

def test_missing_ca_cert_file_fails_fast_with_clear_message(tmp_path):
    missing = tmp_path / "does-not-exist.pem"
    with pytest.raises(ValueError, match="not found"):
        Config(
            url="https://rsc.example.com",
            client_id="id",
            client_secret="secret",
            ca_cert_path=str(missing),
        )


def test_unreadable_ca_cert_file_fails_fast_with_clear_message(tmp_path):
    unreadable = tmp_path / "unreadable.pem"
    unreadable.write_text("not actually checked for readability by mode alone")
    unreadable.chmod(0o000)
    try:
        with pytest.raises(ValueError, match="not readable"):
            Config(
                url="https://rsc.example.com",
                client_id="id",
                client_secret="secret",
                ca_cert_path=str(unreadable),
            )
    finally:
        # Restore permissions so tmp_path cleanup can remove it.
        unreadable.chmod(0o600)


def test_non_pem_ca_cert_file_fails_fast_with_clear_message(tmp_path):
    junk = tmp_path / "not-a-cert.pem"
    junk.write_text("this is definitely not a PEM certificate\n")
    with pytest.raises(ValueError, match="not valid PEM"):
        Config(
            url="https://rsc.example.com",
            client_id="id",
            client_secret="secret",
            ca_cert_path=str(junk),
        )


def test_valid_pem_passes_validation(valid_pem):
    cfg = Config(
        url="https://rsc.example.com",
        client_id="id",
        client_secret="secret",
        ca_cert_path=valid_pem,
    )
    assert cfg.ca_cert_path == valid_pem


# --------------------------------------------------------------------------- #
# rotation warning
# --------------------------------------------------------------------------- #

def test_rotation_warning_emitted_when_ca_cert_path_set(valid_pem, capsys):
    Config(url="https://rsc.example.com", client_id="id", client_secret="secret",
           ca_cert_path=valid_pem)
    err = capsys.readouterr().err
    assert "rotate" in err.lower()
    assert valid_pem in err


def test_rotation_warning_not_emitted_when_unset(capsys):
    Config(url="https://rsc.example.com", client_id="id", client_secret="secret")
    assert capsys.readouterr().err == ""


def test_rotation_warning_fires_once_per_process_not_per_config(valid_pem, capsys):
    Config(url="https://rsc.example.com", client_id="id", client_secret="secret",
           ca_cert_path=valid_pem)
    capsys.readouterr()  # drain the first warning
    Config(url="https://rsc2.example.com", client_id="id2", client_secret="secret2",
           ca_cert_path=valid_pem)
    assert capsys.readouterr().err == ""
