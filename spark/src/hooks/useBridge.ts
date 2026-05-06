/**
 * Typed `fetch` wrapper over the K1 bridge (ADR-0003).
 *
 * Bridge URL and bearer token are read from Vite env vars at build time:
 *   - `VITE_BRIDGE_URL`   (default: http://127.0.0.1:8765)
 *   - `VITE_BRIDGE_TOKEN` (required; throws if missing on first call)
 *
 * The hook itself is currently a stub — K2 only wires types and the fetch
 * surface. K3 will add React state (loading / error / data) plus retries.
 */

import type {
  PersonaCompileRequest,
  PersonaCompileResponse,
  PersonaListItem,
  RetrievalResponse,
  StatusResponse,
} from '../types';

const BRIDGE_URL: string =
  (import.meta.env.VITE_BRIDGE_URL as string | undefined) ?? 'http://127.0.0.1:8765';

function authHeaders(): HeadersInit {
  const token = import.meta.env.VITE_BRIDGE_TOKEN as string | undefined;
  if (!token) {
    throw new Error(
      'VITE_BRIDGE_TOKEN is not set. Copy spark/.env.example to spark/.env.local ' +
        'and set it to match SPARK_BRIDGE_TOKEN exported when running uvicorn.',
    );
  }
  return { Authorization: `Bearer ${token}` };
}

async function getJson<T>(path: string, params?: Record<string, string | number | boolean>): Promise<T> {
  const url = new URL(path, BRIDGE_URL);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      url.searchParams.set(k, String(v));
    }
  }
  const res = await fetch(url.toString(), {
    method: 'GET',
    headers: authHeaders(),
    credentials: 'omit',
    mode: 'cors',
  });
  if (!res.ok) {
    throw new Error(`Bridge GET ${path} failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

async function postJson<TReq, TRes>(path: string, body: TReq): Promise<TRes> {
  const url = new URL(path, BRIDGE_URL);
  const res = await fetch(url.toString(), {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    credentials: 'omit',
    mode: 'cors',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`Bridge POST ${path} failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as TRes;
}

export interface BridgeClient {
  retrieve: (q: string, opts?: { topK?: number; allowStale?: boolean }) => Promise<RetrievalResponse>;
  status: () => Promise<StatusResponse>;
  listPersonas: () => Promise<PersonaListItem[]>;
  compilePersona: (req: PersonaCompileRequest) => Promise<PersonaCompileResponse>;
}

/**
 * Stable bridge client. The hook is intentionally not stateful — components
 * own their own loading/error state via React's built-in primitives.
 */
export function useBridge(): BridgeClient {
  return {
    retrieve: (q, opts) => {
      const params: Record<string, string | number | boolean> = { q };
      if (opts?.topK !== undefined) params.top_k = opts.topK;
      if (opts?.allowStale !== undefined) params.allow_stale = opts.allowStale;
      return getJson<RetrievalResponse>('/retrieve', params);
    },
    status: () => getJson<StatusResponse>('/status'),
    listPersonas: () => getJson<PersonaListItem[]>('/persona/list'),
    compilePersona: (req) => postJson<PersonaCompileRequest, PersonaCompileResponse>('/persona/compile', req),
  };
}
