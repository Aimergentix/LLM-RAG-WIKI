# ADR-0002: Glossary indexing via mirrored concept page

- **Date:** 2026-05-01
- **Status:** accepted

## Implementation status

All five decisions landed in the same revision that accepted this ADR:

1. **Mirror written on W3.** [`src/wiki/ingest.py`](../src/wiki/ingest.py)
   adds `wiki/concepts/_glossary.md` to the atomic write plan after the
   glossary patch. The mirror is regenerated from the *post-patch* schema
   so it tracks both manual and auto rows.
2. **Format.** [`src/wiki/glossary.py`](../src/wiki/glossary.py)
   `render_mirror(schema_md, today)` emits frontmatter
   `generated_by: glossary-mirror`, alphabetical (case-insensitive) H2
   sections, and a `[SCHEMA.md](../../SCHEMA.md#glossary)` source link.
3. **Atomicity.** Reuses `_atomic_write_all` (temp → fsync → `os.replace`),
   inheriting the M3 ingest writer contract.
4. **RAG transparency.** No special-casing in `src/rag/`. The mirror is
   chunked, embedded, and retrieved like any other concept page.
5. **Lint exemption.** [`src/wiki/graph_lint.py`](../src/wiki/graph_lint.py)
   defines `_GENERATED_BASENAMES = {"_glossary.md"}` and skips both
   `orphan` and `index_gap` for matching basenames. `broken_link` still
   applies.

W5 cron-driven regeneration is not yet wired (the W3 hook currently keeps
the mirror in step on every ingest). If a deploy edits `SCHEMA.md`
directly without ingesting, the mirror lags until the next ingest. A
follow-up that calls `render_mirror` from a lint-time refresh hook is
acceptable but unnecessary for the failure mode this ADR targets.


## Context

The wiki layer maintains a domain glossary in `SCHEMA.md ## Glossary`,
extended lazily during W3 ingest whenever a new domain term appears
(see [MASTER.md §6 W3 step 6](../MASTER.md#w3--ingest)).

The RAG layer indexes only files under `wiki_root`, which points at the
`wiki/` folder ([MASTER.md §7 — RAG Schemas](../MASTER.md#rag-schemas)).
`SCHEMA.md` lives at the wiki repo root, not under `wiki/`. Consequence: the
single document that defines domain vocabulary is **never embedded**, so the
RAG layer is structurally blind to the very terms the wiki took care to
define.

Predictable failure mode: a freshly-defined glossary term appears in a query,
no concept page yet covers it in depth, the closest semantic neighbours score
below `min_score`, and the retriever emits `[ERR_INSUFFICIENT_CONTEXT]` or
`[ERR_OUT_OF_DOMAIN]` for a term the wiki demonstrably knows.

This is a silent quality regression: nothing in the current pipeline surfaces
it, and the glossary grows monotonically, so the gap widens over time.

## Decision

1. **Mirror `SCHEMA.md ## Glossary` into `wiki/concepts/_glossary.md`** on
   every W3 ingest and W5 lint run. The mirror is automation-owned; manual
   edits belong in `SCHEMA.md` and will be overwritten.

2. **Mirror format** — a normal concept page with frontmatter:

   ```markdown
   ---
   type: concept
   confidence: high
   sources: []
   updated: {{DATE}}
   generated_by: glossary-mirror
   ---

   # Glossary

   > Auto-generated from SCHEMA.md ## Glossary. Do not edit by hand.

   ## {Term}
   {Definition}

   **Aliases to avoid:** {aliases or "none"}
   **Source:** [SCHEMA.md](../../SCHEMA.md#glossary)
   ```

   One H2 section per glossary row. Stable ordering: alphabetical by term,
   case-insensitive.

3. **Atomic write** — temp file → fsync → `os.replace`, matching the
   existing M3 ingest writer contract. No partial mirrors visible to RAG
   ingest mid-write.

4. **RAG ingest treats `_glossary.md` like any other concept page.** No
   special casing in the chunker, embedder, or retriever. The leading
   underscore is a hint to humans that the page is generated; the chunker's
   stable-ID derivation (MASTER §7) keeps it identifiable.

5. **Lint rule update** — `graph_lint.py` exempts `_glossary.md` from the
   `orphan` rule (it is generated, not authored) but still checks
   `broken_link` against any external links in definitions.

## Consequences

- **Positive**
  - Glossary terms become retrievable without coupling RAG to `SCHEMA.md`'s
    location, parser, or non-domain content (lint rules, ADR table,
    relation-code definitions).
  - Mirror is self-healing: the next ingest or lint regenerates it from the
    canonical source.
  - Exactly one new file per wiki, with well-defined ownership.
- **Negative**
  - Mirror staleness window between SCHEMA edit and the next W3 / W5 run.
    Bounded by lint cadence (default Mon 06:23 cron, plus every ingest).
  - Adds a small write to W3 and W5; both already perform multiple atomic
    writes, so the marginal cost is negligible.
- **Trade-offs accepted**
  - We do not embed `SCHEMA.md` itself into the RAG index. Doing so would
    pollute retrieval with project-meta content (lint rules, ADR table,
    relation-code vocabulary), which is not domain knowledge.

## Alternatives considered

- **Add `SCHEMA.md` to `wiki_root` for RAG ingest** — rejected: SCHEMA mixes
  domain glossary with project-internal lint and ADR content. Embedding it
  whole would degrade retrieval precision on every domain query.
- **Teach the RAG ingest a special "include `SCHEMA.md ## Glossary`"
  hook** — rejected: couples the RAG layer to the wiki layer's file layout
  and section headings; violates the layer-independence invariant from §1.
- **Inline glossary terms into every concept page** — rejected: massive
  duplication; defeats the purpose of a single canonical glossary; high
  risk of drift between copies.
- **Skip the mirror; rely on users to write a `glossary.md` manually** —
  rejected: contradicts the "lazy glossary" discipline from W3 and
  reintroduces the silent regression this ADR exists to prevent.
