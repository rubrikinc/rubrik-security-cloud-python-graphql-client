"""Shared fixtures for TLS/CA-cert tests.

No certificate is committed to this public repo, and none is generated: the
tests only need a file that OpenSSL accepts as a CA file, so they reuse
certifi's bundle (already a dependency, via requests). Nothing here does a
real TLS handshake, so a genuinely self-signed certificate would buy nothing
and would cost a test-only dependency on `cryptography` to mint one.
"""
import shutil

import certifi
import pytest


@pytest.fixture
def valid_pem(tmp_path):
    """Path to a syntactically valid PEM CA file, copied under tmp_path.

    Copied rather than handed out in place so a test can never mutate the
    installed certifi bundle.
    """
    path = tmp_path / "ca.pem"
    shutil.copyfile(certifi.where(), path)
    return str(path)
