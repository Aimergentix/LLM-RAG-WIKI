# ADR-0003: Spark surface boundary — localhost-only HTTP bridge

- **Date:** 2026-05-02
- **Status:** accepted

## Context

The K-track phases (K0–K3) add a GitHub Spark micro-app as a browser-based UI
surface over the existing three-layer pipeline (Wiki, RAG, MCP). GitHub Spark
runs in GitHub's cloud; the pipeline is designed as fully local with no cloud
data processing.

Without an explicit boundary contract, incremental development could
inadvertently move data processing off-device (e.g., switching ChromaDB to a
cloud vector store, storing query history in GitHub KV, or binding the HTTP
bridge to `0.0.0.0`). Each step appears small; together they hollow out the
"fully local" thesis stated in MASTER.md §1.

## Decision

### 1. Bridge bind address

The HTTP bridge (`src/spark_bridge/`) **must** bind to `127.0.0.1` only.
Binding to `0.0.0.0` or any non-loopback address is prohibited unless a
superseding ADR is accepted that explicitly states the relaxed threat model and
the mitigations in place.

### 2. CORS origin

The bridge's CORS policy **must** allow only `https://spark.github.com`.
Wildcard (`*`) or additional origins require a superseding ADR.

### 3. Route read-only invariant

All retrieval endpoints **must** be `GET`. `POST` is permitted only for
stateless operations (persona compilation, query submission) that do not
write to `wiki/`, `data/chroma/`, `data/manifests/`, or `raw/`. Direct
mutation of pipeline data through the bridge is prohibited.

### 4. Data locality invariant

The following assets **must never be transmitted to any external endpoint**
(including GitHub servers):

- `wiki/` directory contents
- `data/chroma/` index
- `data/manifests/manifest.json`
- `raw/` directory contents
- `personas/` YAML files and compiled profiles

GitHub KV storage (`spark.kv`) is permitted **only** for Spark UI state:
last query string, UI preferences, session token. Never for pipeline data.

### 5. Pipeline modules are read-only dependencies

`src/rag/`, `src/wiki/`, and `src/persona_mcp/` are consumed as Python
imports by the bridge. They **must not be modified** as part of K-track work.
New behaviour is added only in `src/spark_bridge/` and `spark/`.

### 6. Auth

The bridge **must** require a bearer token loaded from an environment variable
(default env key: `SPARK_BRIDGE_TOKEN`). The token must not be hardcoded,
committed, or logged. Requests without a valid token receive `401`.

### 7. Relaxation protocol

Any relaxation of rules 1–6 above requires:
1. A new ADR that supersedes this one, with the specific rule number cited.
2. An explicit statement of the threat model change and the mitigations applied.
3. The ADR must be accepted (status: `accepted`) before any code implementing
   the relaxation is merged.

## Consequences

- The Spark app acts as a read-only steering wheel over a local engine.
- All data processing (embedding, retrieval, persona compilation) happens on
  the user's device.
- The browser receives only the query result (YAML excerpt, compiled persona
  prose) — never raw index data or file contents.
- The fully-local invariant stated in MASTER.md §1 is preserved.

## Compliance checklist (K1 acceptance gate)

Before K1 is considered complete, verify:

- [ ] `app.py` binds `host=os.environ.get("SPARK_BRIDGE_HOST", "127.0.0.1")`
- [ ] CORS middleware lists only `https://spark.github.com`
- [ ] No route writes to `wiki/`, `data/`, or `raw/`
- [ ] Auth middleware rejects requests missing a valid `SPARK_BRIDGE_TOKEN`
- [ ] No secret, token, or persona rule text appears in application logs
- [ ] `pytest tests/` passes without modification to existing test files
