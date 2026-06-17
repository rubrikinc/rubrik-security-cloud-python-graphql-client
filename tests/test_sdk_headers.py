from rsc._version import _sdk_headers, _user_agent, _rsc_client_version


def test_bare_client_sends_only_user_agent():
    # No product supplied -> behavior unchanged: only User-Agent, no Sdk-* headers.
    headers = _sdk_headers()
    assert set(headers) == {"User-Agent"}
    assert headers["User-Agent"] == _user_agent()


def test_product_sets_sdk_language_version_and_user_agent():
    headers = _sdk_headers("rubrik-mcp", "0.2.4")
    assert headers["Sdk-Language"] == "rubrik-mcp"
    assert headers["Sdk-Version"] == "0.2.4"
    ua = headers["User-Agent"]
    assert ua.startswith("rubrik-mcp/0.2.4 (rsc-python-client/")
    assert f"rsc-python-client/{_rsc_client_version()}" in ua
    assert "Python/" in ua
    assert ua.endswith(")")


def test_product_without_version_falls_back_to_client_version():
    # When a product omits its version, report the rsc-client (python client)
    # version rather than "unknown" so the call stays identifiable.
    headers = _sdk_headers("rubrik-mcp")
    assert headers["Sdk-Language"] == "rubrik-mcp"
    assert headers["Sdk-Version"] == _rsc_client_version()
    assert headers["User-Agent"].startswith(f"rubrik-mcp/{_rsc_client_version()} (")
