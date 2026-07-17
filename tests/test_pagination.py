"""Pagination guards in RSCClient.execute():

- non-advancing-cursor guard (stops the infinite page-1 loop),
- truncation warning for both `nodes`/`pageInfo` and `data`/`hasMore`/`nextCursor`
  shapes,
- the `max_records` cap.

All tests use a scripted fake endpoint — no config, auth, or network.
"""
from rsc.client import RSCClient


class _FakeClient(RSCClient):
    """RSCClient whose `endpoint` is a scripted responder (bypasses auth/config)."""

    def __init__(self, responder):
        self._responder = responder
        self.calls = 0

    @property
    def endpoint(self):
        def _call(operation, variables=None, **kw):
            self.calls += 1
            return self._responder(operation, dict(variables or {}), self.calls)
        return _call


def _page(nodes, has_next, end_cursor, count=None):
    conn = {"nodes": list(nodes), "pageInfo": {"hasNextPage": has_next, "endCursor": end_cursor}}
    if count is not None:
        conn["count"] = count
    return {"data": {"c": conn}}


# --------------------------------------------------------------------------- #
# non-advancing-cursor guard (loop)
# --------------------------------------------------------------------------- #

def test_loop_guard_stops_on_nonadvancing_cursor(capsys):
    # Query selects pageInfo but never wires `after`, so the server returns the
    # same page (same endCursor) with hasNextPage=true forever.
    client = _FakeClient(lambda op, v, n: _page([{"id": 1}], True, "C1"))
    result = client.execute("query { c { nodes { id } pageInfo { hasNextPage endCursor } } }")
    assert client.calls <= 2  # did not loop
    assert len(result["data"]["c"]["nodes"]) == 1
    assert "cursor did not advance" in capsys.readouterr().err


def test_loop_guard_handles_none_endcursor(capsys):
    # Some connections return endCursor=None with hasNextPage=true; the guard
    # must still detect the non-advancing cursor and stop.
    client = _FakeClient(lambda op, v, n: _page([{"id": 1}], True, None))
    client.execute("query { c { nodes { id } pageInfo { hasNextPage endCursor } } }")
    assert client.calls <= 2
    assert "cursor did not advance" in capsys.readouterr().err


def test_correct_pagination_still_works(capsys):
    def responder(op, variables, n):
        if variables.get("after") is None:
            return _page([{"id": 1}], True, "P1")
        assert variables["after"] == "P1"
        return _page([{"id": 2}], False, "P2")
    client = _FakeClient(responder)
    result = client.execute(
        "query($after: String){ c(after:$after){ nodes { id } pageInfo { hasNextPage endCursor } } }"
    )
    assert [n["id"] for n in result["data"]["c"]["nodes"]] == [1, 2]
    assert "cursor did not advance" not in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# truncation guard — nodes/count and data/hasMore/nextCursor shapes
# --------------------------------------------------------------------------- #

def test_truncation_relay_no_pageinfo(capsys):
    resp = {"data": {"slaDomains": {"nodes": [{"id": i} for i in range(1000)], "count": 1500}}}
    _FakeClient(lambda op, v, n: dict(resp)).execute("q")
    assert "1000 of 1500" in capsys.readouterr().err


def test_truncation_data_hasmore(capsys):
    resp = {"data": {"x": {"data": [{"id": 1}, {"id": 2}], "hasMore": True, "nextCursor": "C"}}}
    _FakeClient(lambda op, v, n: dict(resp)).execute("q")
    assert "2 records (first page only)" in capsys.readouterr().err


def test_truncation_data_total(capsys):
    resp = {"data": {"x": {"data": [{"id": 1}], "total": 50, "hasMore": True}}}
    _FakeClient(lambda op, v, n: dict(resp)).execute("q")
    assert "1 of 50" in capsys.readouterr().err


def test_no_false_positive_complete(capsys):
    resp = {"data": {"x": {"data": [{"id": 1}], "hasMore": False}}}
    _FakeClient(lambda op, v, n: dict(resp)).execute("q")
    assert capsys.readouterr().err == ""


def test_no_false_positive_final_page_cursor(capsys):
    # hasMore=False but a cursor is still populated -> not "more available".
    resp = {"data": {"x": {"data": [{"id": 1}], "hasMore": False, "nextCursor": "X"}}}
    _FakeClient(lambda op, v, n: dict(resp)).execute("q")
    assert capsys.readouterr().err == ""


def test_cursor_only_fallback(capsys):
    # hasMore absent -> fall back to nextCursor presence.
    resp = {"data": {"x": {"data": [{"id": 1}], "nextCursor": "X"}}}
    _FakeClient(lambda op, v, n: dict(resp)).execute("q")
    assert "first page only" in capsys.readouterr().err


def test_truncation_warns_per_field(capsys):
    # A response can carry more than one truncated connection-shaped field
    # (one nodes/count, one data/hasMore) — warn for each.
    resp = {"data": {
        "a": {"nodes": [{"id": 1}], "count": 10},        # Relay, no pageInfo
        "b": {"data": [{"id": 2}], "hasMore": True},      # data/hasMore
    }}
    _FakeClient(lambda op, v, n: dict(resp)).execute("q")
    err = capsys.readouterr().err
    assert "'a'" in err and "'b'" in err


def test_truncation_scans_field_alongside_paginated_connection(capsys):
    # The auto-paginated connection ('c') exhausts cleanly, but a sibling
    # 'data'/'hasMore' field ('side') is truncated. The scan must run over all
    # fields, not just when no connection was found, so 'side' is still flagged.
    resp = {"data": {
        "c": {"nodes": [{"id": 1}], "pageInfo": {"hasNextPage": False, "endCursor": "E"}},
        "side": {"data": [{"id": 2}], "hasMore": True},
    }}
    _FakeClient(lambda op, v, n: dict(resp)).execute("q")
    err = capsys.readouterr().err
    assert "'side'" in err
    assert "'c'" not in err  # the exhausted connection is not flagged


def test_truncation_second_relay_connection(capsys):
    # Only the first connection is auto-paginated; a second Relay connection
    # ('c2') with hasNextPage=true must still be reported as truncated.
    resp = {"data": {
        "c1": {"nodes": [{"id": 1}], "pageInfo": {"hasNextPage": False, "endCursor": "E"}},
        "c2": {"nodes": [{"id": 2}], "pageInfo": {"hasNextPage": True, "endCursor": "F"}},
    }}
    _FakeClient(lambda op, v, n: dict(resp)).execute("q")
    assert "'c2'" in capsys.readouterr().err


def test_returned_pageinfo_reflects_truncation_when_capped():
    # When max_records caps the result, the returned pageInfo.hasNextPage must
    # stay true so a consumer that only sees the return value (not stderr) can
    # detect the result is incomplete.
    def responder(op, variables, n):
        if variables.get("after") is None:
            return _page([{"id": i} for i in range(1000)], True, "P1", count=1500)
        return _page([{"id": i} for i in range(1000, 2000)], True, "P2", count=1500)
    client = _FakeClient(responder)
    result = client.execute(
        "query($after:String){ c(after:$after){ count nodes { id } pageInfo { hasNextPage endCursor } } }",
        max_records=500,
    )
    assert result["data"]["c"]["pageInfo"]["hasNextPage"] is True


def test_returned_pageinfo_false_when_complete():
    # A fully-drained connection must report hasNextPage=false on return.
    def responder(op, variables, n):
        if variables.get("after") is None:
            return _page([{"id": 1}], True, "P1")
        return _page([{"id": 2}], False, "P2")
    client = _FakeClient(responder)
    result = client.execute(
        "query($after:String){ c(after:$after){ nodes { id } pageInfo { hasNextPage endCursor } } }"
    )
    assert result["data"]["c"]["pageInfo"]["hasNextPage"] is False


def test_max_records_zero_returns_no_records(capsys):
    # max_records=0 is a real cap (0 records), not "unbounded". A falsy-check
    # would treat it as no cap and paginate the whole connection.
    def responder(op, variables, n):
        return _page([{"id": i} for i in range(1000)], True, "P1", count=1500)
    client = _FakeClient(responder)
    result = client.execute(
        "query($after:String){ c(after:$after){ count nodes { id } pageInfo { hasNextPage endCursor } } }",
        max_records=0,
    )
    assert len(result["data"]["c"]["nodes"]) == 0
    assert client.calls == 1  # did not paginate


def test_non_bool_hasmore_string_true(capsys):
    # Some endpoints emit hasMore as a string. "true" must read as more-available.
    resp = {"data": {"x": {"data": [{"id": 1}], "hasMore": "true"}}}
    _FakeClient(lambda op, v, n: dict(resp)).execute("q")
    assert "first page only" in capsys.readouterr().err


def test_non_bool_hasmore_string_false(capsys):
    # "false" (string) must not false-positive as more-available.
    resp = {"data": {"x": {"data": [{"id": 1}], "hasMore": "false", "nextCursor": "X"}}}
    _FakeClient(lambda op, v, n: dict(resp)).execute("q")
    assert capsys.readouterr().err == ""


# --------------------------------------------------------------------------- #
# max_records cap
# --------------------------------------------------------------------------- #

def test_max_records_caps_pagination(capsys):
    def responder(op, variables, n):
        if variables.get("after") is None:
            return _page([{"id": i} for i in range(1000)], True, "P1", count=1500)
        return _page([{"id": i} for i in range(1000, 2000)], True, "P2", count=1500)
    client = _FakeClient(responder)
    result = client.execute(
        "query($after:String){ c(after:$after){ count nodes { id } pageInfo { hasNextPage endCursor } } }",
        max_records=500,
    )
    assert len(result["data"]["c"]["nodes"]) == 500
    assert client.calls == 1  # stopped after the first page (1000 >= 500)
    assert "fetching first 500" in capsys.readouterr().err
