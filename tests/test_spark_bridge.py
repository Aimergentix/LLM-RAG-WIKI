"""K1 acceptance tests for the Spark bridge.

These tests verify the FastAPI surface in isolation from the heavy RAG
backends (no model downloads, no Chroma index required). End-to-end
retrieval is exercised via stub embedder/adapter injection per ADR-0003 §6
test-mode contract.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from spark_bridge import auth as bridge_auth  # noqa: E402
from spark_bridge.app import create_app  # noqa: E402

TOKEN = "test-token-deadbeef"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """FastAPI test client with the bearer token configured."""
    monkeypatch.setenv(bridge_auth.TOKEN_ENV_VAR, TOKEN)
    # Reset cached factories between tests so config / store changes take effect.
    from spark_bridge.routes import persona as persona_mod
    from spark_bridge.routes import retrieve as retrieve_mod

    retrieve_mod._config.cache_clear()
    retrieve_mod._embedder.cache_clear()
    retrieve_mod._adapter.cache_clear()
    retrieve_mod._reranker.cache_clear()
    persona_mod._store.cache_clear()
    persona_mod._compiler.cache_clear()

    app = create_app()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------- meta / auth

def test_healthz_open(client: TestClient) -> None:
    """Liveness probe is unauthenticated and returns ``ok``."""
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_status_requires_token(client: TestClient) -> None:
    """Authenticated routes reject requests with no bearer token."""
    r = client.get("/status")
    assert r.status_code == 401


def test_status_rejects_wrong_token(client: TestClient) -> None:
    r = client.get("/status", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_503_when_token_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bridge fails closed when ``SPARK_BRIDGE_TOKEN`` is not configured."""
    monkeypatch.delenv(bridge_auth.TOKEN_ENV_VAR, raising=False)
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/status", headers={"Authorization": "Bearer anything"})
        assert r.status_code == 503


# ---------------------------------------------------------------- CORS

def test_cors_locked_to_spark_origin(client: TestClient) -> None:
    """ADR-0003 §2: only ``https://spark.github.com`` is allowed."""
    r = client.options(
        "/status",
        headers={
            "Origin": "https://spark.github.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "https://spark.github.com"


def test_cors_rejects_other_origin(client: TestClient) -> None:
    r = client.options(
        "/status",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Either 400 from CORS middleware or no allow-origin header echoed back.
    assert r.headers.get("access-control-allow-origin") != "https://evil.example.com"


# ---------------------------------------------------------------- /status

def test_status_returns_counts(client: TestClient) -> None:
    """``GET /status`` returns the schema-stable counts payload."""
    r = client.get("/status", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    data = r.json()
    for key in (
        "wiki_root",
        "wiki_page_count",
        "index_dir",
        "index_doc_count",
        "manifest_path",
        "last_ingest_at",
        "manifest_present",
    ):
        assert key in data
    assert isinstance(data["wiki_page_count"], int)
    assert isinstance(data["index_doc_count"], int)
    assert isinstance(data["manifest_present"], bool)


# ---------------------------------------------------------------- /retrieve

def test_retrieve_schema_shape_when_index_missing(client: TestClient) -> None:
    """``GET /retrieve`` returns a schema-compliant error body when the index
    is absent or stale (no model download required)."""
    os.environ["LLM_RAG_WIKI_TEST_STUB_EMBEDDER"] = "1"
    try:
        r = client.get(
            "/retrieve",
            params={"q": "what is the canonical wiki layout?"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    finally:
        os.environ.pop("LLM_RAG_WIKI_TEST_STUB_EMBEDDER", None)

    # Whether the index exists in the dev workspace or not, the response must
    # match the wire schema and never expose a 5xx unhandled trace.
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {
        "status",
        "query",
        "results",
        "degradation_meta",
        "error_code",
        "message",
    }
    assert body["query"] == "what is the canonical wiki layout?"
    assert isinstance(body["results"], list)


def test_retrieve_validates_query_length(client: TestClient) -> None:
    """Empty query is rejected by FastAPI validation (422)."""
    r = client.get(
        "/retrieve",
        params={"q": ""},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------- /persona

def test_persona_compile_404_for_missing(client: TestClient) -> None:
    """Unknown persona ID returns 404, never 500."""
    r = client.post(
        "/persona/compile",
        json={"character": "definitely-not-a-persona", "domains": []},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert r.status_code == 404


def test_persona_compile_empty_selection(client: TestClient) -> None:
    """Empty selection still compiles (meta-directives only)."""
    r = client.post(
        "/persona/compile",
        json={"character": None, "domains": []},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "dense" in body
    assert "structured" in body
    assert "debug" in body
    assert body["dense"].startswith("<P_CTX:")


def test_persona_compile_with_real_persona(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end compile against a temp persona store."""
    monkeypatch.setenv(bridge_auth.TOKEN_ENV_VAR, TOKEN)

    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "tester.yaml").write_text(
        "id: tester\nkind: character\nname: Test Persona\n"
        "rules:\n  - Be terse.\n  - Cite sources.\nstyle_weights: {}\n",
        encoding="utf-8",
    )

    from persona_mcp.store import PersonaStore
    from spark_bridge.routes import persona as persona_mod

    persona_mod._store.cache_clear()
    monkeypatch.setattr(persona_mod, "_store", lambda: PersonaStore(personas_dir))

    app = create_app()
    with TestClient(app) as c:
        r = c.post(
            "/persona/compile",
            json={"character": "tester", "domains": []},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Char:tester" in body["dense"]
    assert "Be terse" in body["debug"]
    assert body["structured"]["summary"]["character"] == "tester"


def test_persona_list_returns_id_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0003 §4: ``GET /persona/list`` exposes IDs but never rule text."""
    monkeypatch.setenv(bridge_auth.TOKEN_ENV_VAR, TOKEN)

    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "alpha.yaml").write_text(
        "id: alpha\nkind: character\nname: Alpha\nversion: 1.0.0\n"
        "rules:\n  - SECRET-RULE-DO-NOT-LEAK\nstyle_weights: {}\n",
        encoding="utf-8",
    )
    (personas_dir / "beta.yaml").write_text(
        "id: beta\nkind: domain\nname: Beta\nversion: 2.0.0\n"
        "rules:\n  - ANOTHER-SECRET\nstyle_weights: {}\n",
        encoding="utf-8",
    )

    from persona_mcp.store import PersonaStore
    from spark_bridge.routes import persona as persona_mod

    persona_mod._store.cache_clear()
    monkeypatch.setattr(persona_mod, "_store", lambda: PersonaStore(personas_dir))

    app = create_app()
    with TestClient(app) as c:
        r = c.get("/persona/list", headers={"Authorization": f"Bearer {TOKEN}"})

    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 2
    ids = {p["id"] for p in body}
    assert ids == {"alpha", "beta"}
    for p in body:
        assert set(p.keys()) == {"id", "kind", "name", "version"}
    # Defence in depth: no rule text in the response body anywhere.
    raw = r.text
    assert "SECRET-RULE-DO-NOT-LEAK" not in raw
    assert "ANOTHER-SECRET" not in raw


# ---------------------------------------------------------------- K3 integration

def test_k3_full_flow_via_http(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """K3 integration: list -> compile -> status -> retrieve over the HTTP layer.

    Exercises every K1+K3 endpoint that the Spark UI calls, in order, with
    realistic auth and a temp persona store. Backends are stubbed so no model
    download or live ChromaDB is required.
    """
    monkeypatch.setenv(bridge_auth.TOKEN_ENV_VAR, TOKEN)
    monkeypatch.setenv("LLM_RAG_WIKI_TEST_STUB_EMBEDDER", "1")

    personas_dir = tmp_path / "personas"
    personas_dir.mkdir()
    (personas_dir / "researcher.yaml").write_text(
        "id: researcher\nkind: character\nname: Researcher\n"
        "rules:\n  - Cite primary sources.\nstyle_weights: {}\n",
        encoding="utf-8",
    )

    from persona_mcp.store import PersonaStore
    from spark_bridge.routes import persona as persona_mod
    from spark_bridge.routes import retrieve as retrieve_mod

    persona_mod._store.cache_clear()
    retrieve_mod._config.cache_clear()
    retrieve_mod._embedder.cache_clear()
    retrieve_mod._adapter.cache_clear()
    retrieve_mod._reranker.cache_clear()
    monkeypatch.setattr(persona_mod, "_store", lambda: PersonaStore(personas_dir))

    headers = {"Authorization": f"Bearer {TOKEN}"}
    app = create_app()
    with TestClient(app) as c:
        # 1. List personas (Spark mounts the selector with this).
        r_list = c.get("/persona/list", headers=headers)
        assert r_list.status_code == 200
        ids = {p["id"] for p in r_list.json()}
        assert "researcher" in ids

        # 2. Compile a persona profile (stateless).
        r_compile = c.post(
            "/persona/compile",
            json={"character": "researcher", "domains": []},
            headers=headers,
        )
        assert r_compile.status_code == 200
        assert "Char:researcher" in r_compile.json()["dense"]

        # 3. Status snapshot.
        r_status = c.get("/status", headers=headers)
        assert r_status.status_code == 200
        assert "wiki_page_count" in r_status.json()

        # 4. Retrieve. The index may be missing in CI; we only assert
        # schema-compliance, not that results are non-empty.
        r_ret = c.get(
            "/retrieve",
            params={"q": "any local question"},
            headers=headers,
        )
        assert r_ret.status_code == 200
        body = r_ret.json()
        assert body["query"] == "any local question"
        assert isinstance(body["results"], list)

