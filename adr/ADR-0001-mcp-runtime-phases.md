# ADR-0001: MCP runtime phases (S-series) and error classes

- **Date:** 2026-05-01
- **Status:** accepted (partial — see Implementation status)

## Implementation status

- **Decision 1 (rename M1→S0–S5):** applied to `MASTER.md` §6 header and §13 reference.
- **Decision 2 (§9 MCP error class table):** applied; see `MASTER.md` §9 *MCP Error Classes*.
- **Decision 3 (personas/ privacy boundary, localhost-only bind, `[ERR_MCP_BIND]`):** moot for the current stdio transport (`src/persona_mcp/server.py` calls `mcp.run()` with no host bind). `[ERR_MCP_BIND]` reserved in §9 for the future HTTP/socket transport; bind enforcement to be implemented when that transport lands.
- **Decision 4 (§13 reference rewrite):** applied.

## Context

`MASTER.md` defines two phase systems with crisp identifiers and per-phase
contracts:

- **W0–W6** — wiki runtime phases (recurring, per invocation).
- **P1–P5** — RAG build sub-phases (recurring, per implementation pass).

The MCP / persona layer has neither. It is described in §6 as a single block
labelled **"M1"**, while [Appendix F](../MASTER.md#appendix-f--rebuild-module-registry)
freezes the rebuild module registry as **M0–M13**, where `M1 = "Scaffold +
templates"`. The token `M1` therefore names two unrelated things:

- a runtime/operational concept (the MCP layer), and
- a frozen historical artifact (a wiki-builder rebuild module).

This violates the project's own terminology-discipline rule (one naming axis
per concept; no reuse across version / layer / state / artifact).

The MCP layer also lacks the structural scaffolding the other two layers have:

- no per-phase contract analogous to W1–W6 or P1–P5,
- no error class table analogous to [§9](../MASTER.md#9-errors),
- no defined precedence-violation or compilation-failure failure modes.

These gaps are blocking before any further MCP feature work.

## Decision

1. **Rename the MCP runtime track to `S0–S5`** ("Server" phases) and reserve
   the `M*` namespace exclusively for the frozen rebuild registry in
   Appendix F. Mapping:

   | ID | Phase | Scope |
   |---|---|---|
   | `S0` | Plan | Persona inventory, meta-directive review, target client matrix |
   | `S1` | Store | Read/write `personas/*.yaml`, validate schema, append `audit_log` |
   | `S2` | Compile | Deterministic persona → runtime profile; same input ⇒ same output |
   | `S3` | Serve | MCP server bind (localhost only by default), persona resources, `active.yaml` persistence |
   | `S4` | Audit / Rotate | Diff `audit_log` since last rotation; produce reversible change set |
   | `S5` | Advanced (optional) | Multi-persona blending, per-client overrides, remote-control surfaces |

   Phase strictness rule from §4 applies: no `S(N+1)` without explicit Go.

2. **Add an MCP error class table to §9**, parallel in form to the RAG error
   table:

   | Code | Condition |
   |---|---|
   | `[ERR_PERSONA_NOT_FOUND]` | Requested persona id missing from `personas/`. |
   | `[ERR_PERSONA_SCHEMA]` | Persona file fails schema validation. |
   | `[ERR_COMPILE]` | Compilation produced non-deterministic or empty output. |
   | `[ERR_PRECEDENCE]` | Persona attempted to override system / task instructions. |
   | `[ERR_MCP_INJECTION]` | Persona content contains control-language patterns (per §8). |
   | `[ERR_MCP_BIND]` | Server attempted non-localhost bind without explicit `allow_remote: true`. |
   | `[ERR_MCP_RUNTIME]` | Unexpected runtime error in the MCP server. |

3. **Apply the read-only / privacy boundary from §8 to `personas/`**:
   - `personas/` is treated as user-private; never logged in full, never
     emitted to any external endpoint.
   - The MCP server defaults to `127.0.0.1` bind. Remote bind requires an
     explicit `allow_remote: true` config flag and triggers `[ERR_MCP_BIND]`
     otherwise.

4. **Update §13 Agent Entry Points** to reference `MASTER.md §6 (MCP, S0–S5)`
   instead of "§6 (MCP)".

## Consequences

- **Positive**
  - Terminology discipline restored: `M*` and `S*` no longer collide.
  - MCP layer reaches structural parity with Wiki (W) and RAG (P).
  - Compilation, precedence, and bind failures get first-class error codes
    rather than collapsing to generic runtime errors.
  - Persona privacy boundary stops being an unstated assumption.
- **Negative**
  - Existing references to "M1 (MCP)" in commits, issues, or external notes
    become stale. One-time grep + rewrite required.
  - Adds one short table to §9 and one short subsection to §6.
- **Trade-offs accepted**
  - The `S` letter is taken at the cost of any future "Search" or "Storage"
    phase track. Acceptable: those would belong inside W or P, not as a
    fourth layer.

## Alternatives considered

- **Keep `M1` as the MCP runtime label** — rejected: the collision with
  Appendix F is the entire problem this ADR exists to fix.
- **Use `MCP1–MCP5`** — rejected: verbose; breaks the one-letter convention
  of `W` and `P`; reads awkwardly in tables.
- **Fold MCP under `P` (treat persona delivery as a RAG phase)** — rejected:
  MCP has no dependency on the RAG index; the layers are independently
  releasable per §1.
- **Use `M14+` for MCP runtime** — rejected: Appendix F explicitly freezes
  the M-series and forbids further appends.
