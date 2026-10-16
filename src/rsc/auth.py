import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional

import requests

from .config import Config
from ._version import _user_agent


class TokenManager:
    def __init__(self, config: Config):
        self._config = config
        self._rsc_dir = Path.home() / ".rsc"
        self._rsc_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Key on the credential, not just the tenant, so a service account and a
        # PAT for the same tenant never share (and silently swap) a cached token.
        cache_key = f"{config.url}|{config.client_id}"
        key_hash = hashlib.sha256(cache_key.encode()).hexdigest()[:12]
        self._cache_file = self._rsc_dir / f"token_cache_{key_hash}.json"

    def get_token(self) -> str:
        cached = self._load_cache()
        if cached and cached.get("expires_at", 0) > time.time() + 60:
            return cached["access_token"]
        return self._fetch_token()

    def _load_cache(self) -> Optional[dict]:
        if not self._cache_file.exists():
            return None
        try:
            with open(self._cache_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _fetch_token(self) -> str:
        # `requests` and `urllib` (used for the GraphQL calls in client.py) each
        # consult a different default trust store, so `verify` must be threaded
        # through here explicitly rather than relying on an ambient env var.
        # When ca_cert_path is unset, `verify=True` reproduces today's default
        # behavior (validate against the certifi bundle) exactly.
        resp = requests.post(
            self._config.token_uri,
            json={
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "grant_type": "client_credentials",
            },
            headers={"User-Agent": _user_agent()},
            timeout=30,
            verify=self._config.ca_cert_path or True,
        )
        if resp.status_code == 403 and self._config.token_uri.endswith("/api/pat_login"):
            # RSC returns 403 (not 401) when the tenant hasn't enabled personal
            # access tokens; surface that rather than a generic HTTP error.
            raise PermissionError(
                "Personal access token login was rejected (HTTP 403). The "
                "Personal Access Token feature may not be enabled on this RSC "
                f"tenant: {resp.text}"
            )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        cache = {"access_token": token, "expires_at": time.time() + expires_in}
        fd = os.open(self._cache_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(cache, f)
        return token
