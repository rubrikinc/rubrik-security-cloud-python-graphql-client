import json
import os
import stat
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class Config:
    url: str
    client_id: str
    client_secret: str = field(repr=False)
    token_uri: str = field(default=None)

    def __post_init__(self):
        parsed = urlparse(self.url)
        if parsed.scheme != "https":
            raise ValueError(
                f"RSC URL must use HTTPS (got scheme '{parsed.scheme}'): {self.url}"
            )
        if self.token_uri is None:
            self.token_uri = f"{self.url}/api/client_token"


def _warn_if_open_permissions(path) -> None:
    """Emit a warning if the credential file has group or other read bits set."""
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return
    if mode & 0o077:
        warnings.warn(
            f"Credential file '{path}' has open permissions "
            f"({stat.filemode(mode)}). Restrict to 0o600 to protect your credentials.",
            stacklevel=3,
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
    return Config(
        url=url,
        client_id=sa["client_id"],
        client_secret=sa["client_secret"],
        token_uri=token_uri,
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

    missing = [name for name, val in [("url", url), ("client_id", client_id), ("client_secret", client_secret)] if not val]
    if missing:
        raise ValueError(f"Missing required RSC config fields: {', '.join(missing)}")

    return Config(url=url, client_id=client_id, client_secret=client_secret)
