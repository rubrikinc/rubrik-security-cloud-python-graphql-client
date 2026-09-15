import json
import os
import ssl
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

_warned_self_signed_cert = False


@dataclass
class Config:
    url: str
    client_id: str
    client_secret: str = field(repr=False)
    token_uri: str = field(default=None)
    ca_cert_path: str = field(default=None)

    def __post_init__(self):
        parsed = urlparse(self.url)
        if parsed.scheme != "https" and os.environ.get("RSC_INSECURE_HTTP") != "1":
            raise ValueError(
                f"RSC URL must use HTTPS (got scheme '{parsed.scheme}'): {self.url}"
            )
        if self.token_uri is None:
            self.token_uri = f"{self.url}/api/client_token"
        if self.ca_cert_path is not None:
            _validate_ca_cert(self.ca_cert_path)
            _warn_self_signed_cert_once(self.ca_cert_path)


def _warn_if_open_permissions(path) -> None:
    """Emit a warning if the credential file has group or other read bits set."""
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return
    if mode & 0o077:
        print(
            f"WARNING: Credential file '{path}' has open permissions "
            f"({stat.filemode(mode)}). Restrict to 0o600 to protect your credentials.",
            file=sys.stderr,
        )


def _validate_ca_cert(path) -> None:
    """Eagerly validate the CA cert file so a bad path fails fast at config
    load with a clear message, rather than as an opaque handshake error the
    first time a request is made."""
    if not os.path.exists(path):
        raise ValueError(f"CA certificate file not found: {path}")
    if not os.access(path, os.R_OK):
        raise ValueError(f"CA certificate file is not readable: {path}")
    try:
        ssl.create_default_context(cafile=path)
    except ssl.SSLError as e:
        raise ValueError(f"CA certificate file is not valid PEM: {path} ({e})") from e


def _warn_self_signed_cert_once(path) -> None:
    """Warn once per process that a custom trust anchor is configured.

    Trusting a self-signed certificate is a stopgap; recommend rotating to a
    CA-signed certificate (RSC Certificate Management UI / CSR flow).
    """
    global _warned_self_signed_cert
    if _warned_self_signed_cert:
        return
    _warned_self_signed_cert = True
    print(
        f"WARNING: Trusting custom CA certificate '{path}' for RSC connections. "
        "This is intended as a stopgap for a self-signed certificate — rotate to "
        "a CA-signed certificate via the RSC Certificate Management UI as soon "
        "as possible.",
        file=sys.stderr,
    )


def load_config_from_service_account(path) -> "Config":
    _warn_if_open_permissions(path)
    with open(path) as f:
        sa = json.load(f)
    token_uri = sa.get("access_token_uri")
    if not token_uri:
        raise ValueError(f"Service account file missing 'access_token_uri': {path}")
    # Derive base URL by stripping the known token path suffix
    url = token_uri.removesuffix("/api/client_token")
    # Read here too: load_config() hands off to this function and returns, so a
    # caller using a service account file never reaches the env lookup there.
    ca_cert_path = os.environ.get("RSC_CA_CERT_FILE")
    return Config(
        url=url,
        client_id=sa["client_id"],
        client_secret=sa["client_secret"],
        token_uri=token_uri,
        ca_cert_path=ca_cert_path,
    )


def load_config() -> "Config":
    # Service account file takes precedence if specified via env var
    sa_file = os.environ.get("RSC_SERVICE_ACCOUNT_FILE")
    if sa_file:
        return load_config_from_service_account(sa_file)

    config_file = Path.home() / ".rsc" / "config.json"
    file_values = {}
    if config_file.exists():
        _warn_if_open_permissions(config_file)
        with open(config_file) as f:
            file_values = json.load(f)

    # ~/.rsc/config.json can also point at a service account file
    sa_file = file_values.get("service_account_file")
    if sa_file:
        return load_config_from_service_account(sa_file)

    url = os.environ.get("RSC_URL") or file_values.get("url")
    client_id = os.environ.get("RSC_CLIENT_ID") or file_values.get("client_id")
    client_secret = os.environ.get("RSC_CLIENT_SECRET") or file_values.get("client_secret")
    ca_cert_path = os.environ.get("RSC_CA_CERT_FILE")

    missing = [name for name, val in [("url", url), ("client_id", client_id), ("client_secret", client_secret)] if not val]
    if missing:
        raise ValueError(f"Missing required RSC config fields: {', '.join(missing)}")

    return Config(url=url, client_id=client_id, client_secret=client_secret, ca_cert_path=ca_cert_path)
