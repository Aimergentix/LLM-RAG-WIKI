"""K-track HTTP bridge between the GitHub Spark micro-app and the local pipeline.

This package is additive over the existing three-layer pipeline (`src/rag`,
`src/wiki`, `src/persona_mcp`). It binds to ``127.0.0.1`` only and exposes
read-only retrieval plus stateless persona compilation. See ``adr/ADR-0003``
for the binding contract.
"""
