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
        url_hash = hashlib.sha256(config.url.encode()).hexdigest()[:12]
        self._cache_file = self._rsc_dir / f"token_cache_{url_hash}.json"

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
        resp = requests.post(
            self._config.token_uri,
            json={
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "grant_type": "client_credentials",
            },
            headers={"User-Agent": _user_agent()},
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        cache = {"access_token": token, "expires_at": time.time() + expires_in}
        self._cache_file.write_text(json.dumps(cache))
        os.chmod(self._cache_file, 0o600)
        return token
