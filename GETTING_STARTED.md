# GETTING_STARTED

# What this is:

**llm-rag-wiki:** is a fully-local, three-layer personal knowledge stack.

*Wiki layer* (wiki) — converts dropped source files (entry → raw) into a structured, interlinked Markdown knowledge base under wiki (concepts, entities, sources, synthesis), with a bounded relation vocabulary, lazy glossary, graph linter, and optional cron automation.

*RAG layer* (rag) — chunks and embeds the wiki into ChromaDB with deterministic IDs, atomic manifest writes, and a CLI retriever that emits schema-compliant YAML and degrades gracefully ([ERR_INSUFFICIENT_CONTEXT] / [ERR_OUT_OF_DOMAIN]).

*MCP layer* (persona_mcp) — a local MCP server that compiles per-persona profiles (character × domain) plus meta-directives, delivering them as a "personal AI identity layer" to any AI tool. No cloud, no accounts.

*What it establishes:* a single normative spec (MASTER.md) that all editor/agent shims (AGENTS.md, GEMINI.md, SKILL.md, Copilot chatmodes, .cursorrules) merely point to — preventing rule drift across AI clients. Phase-gated builds (W0–W6, P1–P5, M1) require explicit Go before advancing.

*What it does in practice:* drop a file in entry, run autoconvert → ingest → wiki grows with cross-refs and contradictions flagged → RAG re-indexes → any MCP-aware AI session can both query that wiki and adopt your local personas, all without sending anything off-machine.
