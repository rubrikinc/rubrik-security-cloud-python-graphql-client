"""Tests for search_types() — type-level BM25 search."""

from rsc import search_types


def test_search_types_returns_list():
    results = search_types("cluster")
    assert isinstance(results, list)


def test_results_have_name_and_ops_keys():
    results = search_types("cluster")
    assert len(results) > 0
    for r in results:
        assert "name" in r
        assert "ops" in r
        assert "score" in r


def test_cluster_search_returns_cluster_type():
    results = search_types("cluster")
    names = [r["name"] for r in results]
    assert any("Cluster" in n for n in names), f"Expected a Cluster type in results, got: {names}"


def test_cluster_ops_contain_cluster_operations():
    results = search_types("cluster")
    # ClusterConnection is the canonical connection type returned by cluster queries.
    cluster_result = next((r for r in results if r["name"] == "ClusterConnection"), None)
    assert cluster_result is not None, (
        f"ClusterConnection not found in search_types('cluster') top-10; got: "
        f"{[r['name'] for r in results]}"
    )
    assert isinstance(cluster_result["ops"], list)
    assert len(cluster_result["ops"]) > 0
    # At least one op should reference cluster semantics
    ops_lower = [op.lower() for op in cluster_result["ops"]]
    assert any("cluster" in op for op in ops_lower), (
        f"Expected at least one cluster-related op, got: {cluster_result['ops'][:10]}"
    )


def test_scores_positive_for_relevant_results():
    results = search_types("cluster")
    assert len(results) > 0
    for r in results:
        assert r["score"] > 0, f"Expected positive score, got {r['score']} for {r['name']}"


def test_results_capped_at_ten():
    results = search_types("cluster")
    assert len(results) <= 10


def test_ops_is_list_of_strings():
    results = search_types("sla domain policy")
    assert len(results) > 0
    for r in results:
        assert isinstance(r["ops"], list)
        for op in r["ops"]:
            assert isinstance(op, str)


def test_empty_query_returns_list():
    # Even a poor query must return a list (possibly empty), not raise.
    results = search_types("zzzzzunlikelytermzzzzz")
    assert isinstance(results, list)
    assert len(results) == 0
