# Spark app — K2 shell

GitHub Spark micro-app over the local K1 bridge. K2 only ships the
scaffold — no real UI logic.

## Setup

```bash
cd spark
npm install
cp .env.example .env.local
# edit .env.local: set VITE_BRIDGE_TOKEN to match SPARK_BRIDGE_TOKEN
```

## Dev

```bash
# 1. Start the local bridge (in repo root)
SPARK_BRIDGE_TOKEN=$(cat .env.local | grep VITE_BRIDGE_TOKEN | cut -d= -f2) \
  uvicorn src.spark_bridge.app:app --host 127.0.0.1 --port 8765

# 2. Start the Spark dev server
npm run dev
```

## Contract

- See `adr/ADR-0003-spark-surface-boundary.md` for the binding invariants.
- `src/types.ts` is a manual mirror of `src/spark_bridge/schemas.py`.
  Any schema change MUST update both files in the same commit.
