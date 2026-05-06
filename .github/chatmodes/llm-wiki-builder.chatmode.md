---
description: LLM Wiki Builder — Plan/Execute toggle entry point for GitHub Copilot
---

Refer to [MASTER.md](../../MASTER.md) for the unified three-layer
specification. This chatmode is the GitHub Copilot entry point listed in
[MASTER.md §13 Agent Entry Points](../../MASTER.md#13-agent-entry-points);
it delegates to `src/wiki/` and the `MASTER.md §6` phase verbs
(`init`, `autoconvert`, `ingest`, `query`, `lint`, `cron-install` /
`cron-uninstall`).

Pointer-only per MASTER.md §2 (Note on editor shims). Do not duplicate logic.
