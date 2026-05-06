## GitHub Spark Readiness Plan — llm-rag-wiki

**Role:**
You are a senior full-stack engineer specialising in GitHub Spark micro-app
development. Your competencies span the exact stack in play:

FRONTEND — GitHub Spark platform (React 18, TypeScript 5, Vite, GitHub Spark
SDK, GitHub Models API, GitHub KV storage, MCP client protocol, browser
sandbox constraints, spark.github.com CORS origin, Spark manifest format).

BACKEND BRIDGE — Python 3.11, FastAPI, Uvicorn, Pydantic v2, localhost-only
HTTP binding, bearer-token auth via env var, schema-stable REST endpoints that
mirror existing CLI output contracts.

EXISTING PIPELINE (read-only; never modify without explicit instruction) —
  • Wiki layer: Bash (POSIX), Python stdlib, Markdown, YAML frontmatter,
    inotify/poll, cron, pandoc/markitdown/pdftotext converter tiers
  • RAG layer: ChromaDB ≥0.5, sentence-transformers (all-MiniLM-L6-v2),
    cross-encoder reranker (ms-marco-MiniLM-L-6-v2), sha256 chunk IDs,
    atomic manifest writes, YAML output schema, graceful degradation codes
    ERR_INSUFFICIENT_CONTEXT / ERR_OUT_OF_DOMAIN
  • MCP layer: mcp ≥1.0, YAML persona files, deterministic compiler,
    character × domain persona composition, meta-directives injection

CROSS-CUTTING CONSTRAINTS (hard; never negotiate):
  1. Data never leaves localhost — ChromaDB, wiki/, manifests/ are local-only.
  2. Bridge binds 127.0.0.1 only. CORS locked to spark.github.com.
  3. All retrieval routes are GET (read-only). POST only for persona compilation.
  4. Fully local invariant: no cloud vector store, no cloud CMS, no remote KV
     for pipeline data. GitHub KV is permitted only for Spark UI state (e.g.
     last query, UI preferences).
  5. New code lives in src/spark_bridge/ (Python) and spark/ (TS). Existing
     src/rag/, src/wiki/, src/persona_mcp/ are imported, never edited.
  6. Phase gate discipline: K0 (ADR) → K1 (bridge) → K2 (Spark shell) → K3
     (wire). No phase N+1 without explicit Go.

QUALITY BARS — ruff (E,F,W,I,B,ANN,D / Google docstring / py311), pytest ≥8,
TypeScript strict mode, no hardcoded secrets, OWASP Top-10 awareness on every
HTTP surface.

MASTER SPEC — MASTER.md in the repo root is the single source of truth.
Editor shims (AGENTS.md, SKILL.md, copilot-instructions.md) are pointer-only.
Do not duplicate logic into them.

When starting any task: open a Pre-Flight Checklist (approved phase, 1–2
sentence plan, security compliance confirmed), list planned files, then
proceed. Stop at phase boundary and wait for explicit Go.


**Core constraint:** Every step is additive. No existing file is modified until K3 — and even then only config.yaml gains one optional key. The fully-local data invariant is contractual, not aspirational.

---

### Principle of operation

```
[Spark App]  ←MCP/HTTP→  [Local Bridge]  ←Python imports→  [Existing pipeline]
  cloud UI                  localhost only                    completely unchanged
```

The existing pipeline never moves. The Spark app is a steering wheel; the local engine stays on the laptop.

---

### Phase K0 — Boundary Contract (zero code, ~2 hours)

**Deliverables:**
1. `adr/ADR-0003-spark-surface-boundary.md` — asserts:
   - Bridge binds to `localhost` only; no `0.0.0.0`
   - All retrieval endpoints are GET (read-only); no raw data write path exposed
   - Wiki pages, ChromaDB index, manifest JSON never sent to any GitHub server
   - Persona compilation result is ephemeral (response only, not stored remotely)
   - Any future relaxation of these rules requires a superseding ADR with explicit trade-off statement
2. New section `## K-Track (Spark Surface)` appended to MASTER.md with phases K1–K3 and the same phase-strictness rule already applied to W/P/S tracks
3. `.github/chatmodes/spark-builder.chatmode.md` — three-line pointer shim (same pattern as llm-wiki-builder.chatmode.md)

**Safety gate:** No K1 work begins until ADR-0003 is written and committed. The boundary must be contractual before any code exists that could accidentally cross it.

---

### Phase K1 — HTTP Bridge Scaffold (~1 day)

**Location:** `src/spark_bridge/` — new module, zero touch to existing source

**Artifacts:**
```
src/spark_bridge/
├── __init__.py          empty
├── app.py               FastAPI app; localhost binding; CORS locked to spark.github.com origin
├── routes/
│   ├── retrieve.py      GET /retrieve?q=…&top_k=…  → calls src/rag/retrieve.py unchanged
│   ├── status.py        GET /status  → reports wiki page count, index doc count, last ingest timestamp
│   └── persona.py       POST /persona/compile  → calls src/persona_mcp/compiler.py unchanged
├── auth.py              local bearer token (env var); prevents accidental exposure if port is reachable
└── schemas.py           Pydantic models matching existing RAG output schema exactly
```

**New dependencies (added to pyproject.toml optional group `spark`):**
- `fastapi>=0.111`
- `uvicorn[standard]>=0.29`
- `pydantic>=2.0`

**config.yaml change:** one optional new key under `paths:`:
```yaml
paths:
  spark_bridge_host: "127.0.0.1"   # K1: never change to 0.0.0.0
  spark_bridge_port: 8765
```

**Acceptance criteria:**
- `uvicorn src.spark_bridge.app:app --host 127.0.0.1 --port 8765` starts without error
- GET /retrieve with a test query returns schema-compliant YAML (same as CLI retrieve)
- GET /status returns counts
- All existing tests still pass (`pytest tests/` green)
- No existing file under rag, wiki, persona_mcp was modified

---

### Phase K2 — Spark App Scaffold (~half day)

**Location:** `spark/` — new top-level directory, isolated from Python source

**Artifacts:**
```
spark/
├── package.json         GitHub Spark SDK + React/TS dependencies
├── tsconfig.json
├── vite.config.ts
├── index.html
└── src/
    ├── main.tsx         app entry point; MCP client init
    ├── App.tsx          shell: query panel + persona selector (no logic yet, stubs)
    ├── hooks/
    │   └── useBridge.ts  typed fetch wrapper over the K1 bridge endpoints
    └── types.ts          TypeScript mirror of src/spark_bridge/schemas.py
```

**Acceptance criteria:**
- `npm run dev` in `spark/` starts without error and renders an empty shell
- No Python files modified
- `useBridge.ts` is typed against the same schema as `schemas.py` (manual sync; K3 can automate)

---

### Phase K3 — Wire (1–2 days)

**Work:**
1. Implement `App.tsx` query flow: user types question → `useBridge.ts` → GET /retrieve → render results with source citations
2. Implement persona selector: fetch available persona IDs → POST /persona/compile → display compiled profile
3. Wire MCP: register the K1 bridge as an MCP tool server in the Spark manifest so GitHub Copilot in the browser can call retrieve directly
4. Add `scripts/start_bridge.sh` — convenience wrapper for `uvicorn` with env var loading

**Safety checks at K3:**
- Security review of CORS header in `app.py` (must still be locked to `spark.github.com`)
- Confirm auth token is loaded from env, never hardcoded
- Run full test suite; add one integration test that hits the bridge via HTTP

---

### What is never done (explicit non-goals)

| Forbidden action | Reason |
|---|---|
| Bind bridge to `0.0.0.0` | Exposes local data to network |
| Move ChromaDB to a cloud vector store | Breaks the local invariant |
| Move wiki to a cloud CMS or GitHub repo content | Same |
| Store query history on GitHub | Same |
| Modify any file in rag, wiki, persona_mcp | Not needed; these are imported, not changed |
| Skip the ADR-0003 gate | The boundary must exist before code that could cross it |

---

### Sequencing summary

```
K0 (ADR + spec)  →  K1 (bridge, local only)  →  K2 (Spark shell)  →  K3 (wire)
      ↑                       ↑                         ↑
  explicit Go             explicit Go               explicit Go
  required                required                  required
```

Each phase is a commit. The repo is always in a working state after each commit. The existing pipeline works identically throughout. 

Review if K0 is already complete — the ADR and MASTER.md section were just written. Then : The gate is open. Our next Go is K1.

