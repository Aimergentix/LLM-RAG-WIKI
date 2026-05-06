# Deep Improvement Audit Prompt
# for the llm-rag-wiki

## PREAMBLE

You are auditing the llm-rag-wiki repository — a fully-local three-layer pipeline (Wiki builder → ChromaDB RAG → MCP persona server) governed by a
single normative specification (`MASTER.md`) and a frozen rebuild registry (Appendix F, modules M0–M13).

Your job is **not** to add features, refactor for taste, or rewrite working code. Your job is to find the highest-leverage *latent* problems — the ones that will silently degrade quality, correctness, or maintainability over the
next 50 commits — and report them with citations strong enough that a maintainer can act on them without re-investigating.

---

## 0. Operating contract

- **Read-only.** No file writes, no shell mutations, no network calls.
- **Evidence rule.** Every finding cites `path:line` or a verbatim quote.
  No claim without a citation; if you cannot cite, downgrade to `Assumption`.
- **No invention.** Do not invent APIs, error codes, line numbers, CVEs,
  versions, or library functions. If unsure, tag `[API-UNVERIFIED]` or
  `[LANG-UNCERTAIN]` and cap severity at `Major`.
- **Minimum surface.** Do not propose drive-by refactors, speculative
  features, or stylistic preferences. Findings must trace to a concrete
  defect, risk, or contract violation.
- **Terminology discipline.** Define every name on first use. Flag any
  collision where one token denotes >1 axis (version vs. layer vs. state vs.
  artifact). The `M*` / MCP-`M1` collision is a known example and must not
  be the only one you find.

---

## 1. Inputs to read first (in this order, parallel where possible)

1. `MASTER.md` — entire file. This is the contract.
2. `adr/ADR-0001-mcp-runtime-phases.md`, `adr/ADR-0002-glossary-indexing.md`
   — open proposals; treat as `proposed`, not `accepted`.
3. Layer entry points:
   - Wiki: `src/wiki/init.py`, `ingest.py`, `crossref.py`, `glossary.py`,
     `agent_seam.py`, `graph_lint.py`, `query.py`, `query_agent.py`,
     `autoconvert.sh`, `install_cron.sh`.
   - RAG: `src/rag/config.py`, `manifest.py`, `chunker.py`, `embedder.py`,
     `store.py`, `ingest.py`, `retrieve.py`, `_query_store.py`,
     `eval_runner.py`.
   - MCP: `src/persona_mcp/store.py`, `compiler.py`, `server.py`.
4. Tests: `tests/conftest.py` plus every `test_*.py`. Treat tests as the
   *de facto* contract where they disagree with `MASTER.md`.
5. Editor shims: `AGENTS.md`, `GEMINI.md`, `SKILL.md`,
   `.github/copilot-instructions.md`, any `.cursorrules`, any
   `.github/chatmodes/*.md`. Confirm they are pointer-only per §2.
6. Templates: `templates/`, `templates/pages/`.

Do **not** read legacy `LLM_Wiki/`, `RAG-Wiki/`, or `Local_MCP_Server/`
folders unless a specific finding requires it; the rebuild is frozen.

---

## 2. Audit axes (run all six; each finding is tagged with one)

### A. Spec / code conformance
For every normative claim in `MASTER.md` §6–§11 (phases, schemas, security,
errors, OPS, evals), find the implementing code and verify exact match.
Flag every drift:
- error codes emitted by code that are not in §9 (or vice versa);
- config keys / dataclass fields that disagree with §7;
- chunk-ID derivation that disagrees with §7's stated formula;
- CLI exit codes that disagree with §9's table;
- log-format strings that disagree with §7's wiki log grammar;
- security boundaries asserted in §8 that are not enforced in code.

### B. Cross-layer contracts
The pipeline is `entry/ → raw/ → wiki/ → chroma/ → MCP client`. Verify the
seams:
- Does anything mark the RAG manifest dirty when W3 ingest mutates `wiki/`?
- Does the RAG retriever assume manifest freshness it cannot guarantee?
- Does the MCP server have any defined channel to query the RAG (per
  ADR-0001 S-series), or is the persona/RAG triangle structurally broken?
- Does the glossary mirror proposed in ADR-0002 already exist in some
  partial form that would conflict with the proposal?

### C. Determinism, atomicity, concurrency
The spec promises deterministic chunk IDs, atomic manifest writes, and
shadow-collection reindex. For each:
- Is the determinism actually input-only, or does it depend on dict
  iteration order, locale, file-system traversal order, or `os.walk` order?
- Are atomic writes truly `temp → fsync → os.replace`, or are there silent
  partial-write windows (truncate-then-write, missing fsync, missing
  directory fsync)?
- Are there cron + interactive-run race conditions
  (`autoconvert.sh` + `lint_cron.sh`) not guarded by `flock`?
- Are persona files ever read mid-write by the MCP server?

### D. Security posture (against §8)
- Path-escape: does every `Path` resolution call `.resolve()` and verify
  `is_relative_to(wiki_root)` *after* resolution, not before?
- Symlink handling: stated as "not followed by default" — verify per
  call site; one missed `follow_symlinks=False` is a finding.
- Prompt-injection rule: §8 lists trigger phrases. Is there any code that
  detects them, or is the rule purely documentary?
- Secret redaction: §8 forbids logging secrets. Is there any structured
  redaction in the JSONL logger, or only a convention?
- MCP bind: per ADR-0001, default must be `127.0.0.1`. Verify current
  `server.py` behaviour and flag any `0.0.0.0` default.

### E. Anti-hallucination floors in agent-facing prose
The spec is read by LLM agents as their contract. Audit for:
- Ambiguity that admits >1 reasonable reading (cite both readings).
- Underspecified phase boundaries (e.g. what exactly "1 feedback round"
  means in W3 step 3).
- Templates with placeholders that have no defined substitution rule in §7.
- Editor shims that contain *any* normative content beyond a pointer
  (violates §2's pointer-only rule).
- Chatmodes that duplicate logic that lives in `MASTER.md`.

### F. Token economy and operational cost
§10 asserts a token-economy rule but defines no budget. Find:
- Hard upper bound on a compiled persona profile size — is it enforced?
- Hard upper bound on retrieved excerpt length — is `max_context_chars`
  actually consulted by `retrieve.py`?
- Any prose in `MASTER.md` that duplicates content from `templates/`,
  `config.yaml`, or test fixtures (single source of truth violation).
- Per-phase prompt length when rendered by `scripts/run_phase.sh` —
  estimate token count; flag if >2 KB without justification.

---

## 3. Phases of work

1. **Intake.** List the files you read; note any that were unreadable,
   empty (e.g. `src/wiki/0001-v2-consolidated-layout.md`), or stale.
2. **Decomposition.** For each layer, enumerate (entry points, side
   effects, external dependencies, persistence). One sentence each.
3. **Structural trace.** Walk the data flow `entry/ → raw/ → wiki/ →
   chroma/ → MCP client` end to end. Note every place where an invariant
   from §7 or §8 must hold but is not statically verifiable.
4. **Criterion check.** For each axis A–F above, produce findings.
5. **Gap analysis.** What does `MASTER.md` *not* cover that a maintainer
   would need within the next 6 months? (One-line gaps only; do not
   propose solutions here.)
6. **Synthesis.** Emit the report below.

After steps 3 and 5, emit one line:
`Contract-State: reviewed X of Y sections; outstanding: [gap]`.

---

## 4. Output format (strict)

```
## Audit Summary
- Artifact: llm-rag-wiki @ <git rev or "working tree">
- Verdict: PASS | CONDITIONAL PASS | FAIL
- Expansion-Ready: YES | NO | REQUIRES REMEDIATION
- Critical: N   Major: N   Minor: N   Suggestion: N
- Confidence in verdict: 0–100%

## Expansion-Ready Rationale
[1–3 sentences citing finding IDs. If REQUIRES REMEDIATION, name the
minimum blocking finding IDs.]

## Findings
[FINDING-NN] Title
- Observation: <fact, with path:line or verbatim quote>
- Axis: A | B | C | D | E | F
- Category: Correctness | Maintainability | Idiomatic Fit | Risk | Clarity | Style
            (+ optional tag: [LANG-UNCERTAIN] | [API-UNVERIFIED] | [INTENT-UNKNOWN])
- Severity: Critical | Major | Minor | Suggestion
- Status: Verified | Assumption | Discourse
- Confidence: 0–100%
- Recommendation: <single concrete action; no alternatives>

## Recommended Next Action
<single most impactful step, with finding IDs it resolves>

## Gap List (no solutions)
- <one-line gap>
- <one-line gap>
```

---

## 5. Severity ceilings (hard limits — never override)

- `Status: Assumption` ⇒ severity ≤ `Major`.
- Any uncertainty tag (`[LANG-UNCERTAIN]`, `[API-UNVERIFIED]`,
  `[INTENT-UNKNOWN]`) ⇒ severity ≤ `Major`.
- Security finding without a reproducible trigger path ⇒ ≤ `Major`,
  status `Assumption`.
- Confidence < 60% ⇒ status `Assumption` or `Discourse`.

---

## 6. Out of scope (do not emit findings for any of these)

- Performance micro-optimizations.
- Style / formatting / line-length / import-order.
- Library replacements ("use httpx instead of requests").
- Type-annotation density on already-working code.
- Test-coverage percentage as a number (cite specific untested branches
  instead, if any).
- Documentation prose quality (clarity findings must trace to actual
  ambiguity, not voice or tone).
- Suggestions to "consider" anything. Every recommendation is concrete.

---

## 7. Pre-output self-check

Before emitting, verify:
- Every finding has Observation + Axis + Category + Severity + Status +
  Confidence + Recommendation.
- Every Observation cites a real file/line or quotes verbatim.
- No invented identifiers, line numbers, or APIs.
- No drive-by refactor recommendations.
- Severity ceilings respected.
- Gap list contains no solutions.
- Recommended Next Action names finding IDs.

If any check fails, fix the report; do not emit.
```

This prompt is calibrated to this repo's specific structure (three layers, MASTER.md as contract, frozen M-registry, the two open ADRs) and to the project's own audit-core rules (audit-core.instructions.md), so findings will arrive in the same shape your existing review pipeline expects.  


