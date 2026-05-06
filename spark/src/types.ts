/**
 * TypeScript mirror of `src/spark_bridge/schemas.py`.
 *
 * Manually kept in sync (K2). K3 may automate this via a generator that
 * reads the FastAPI OpenAPI document. Until then, any schema change in
 * `schemas.py` MUST be reflected here in the same commit.
 */

// ---- /retrieve --------------------------------------------------------------

export interface RetrievalResult {
  score: number;
  source: string;
  heading: string;
  chunk_id: string;
  excerpt: string;
}

export interface RetrievalResponse {
  status: string;
  query: string;
  results: RetrievalResult[];
  degradation_meta: Record<string, unknown> | null;
  error_code: string | null;
  message: string | null;
}

// ---- /status ----------------------------------------------------------------

export interface StatusResponse {
  wiki_root: string;
  wiki_page_count: number;
  index_dir: string;
  index_doc_count: number;
  manifest_path: string;
  last_ingest_at: string | null;
  manifest_present: boolean;
}

// ---- /persona/compile -------------------------------------------------------

export interface PersonaListItem {
  id: string;
  kind: string;
  name: string;
  version: string;
}

export interface PersonaCompileRequest {
  character: string | null;
  domains: string[];
}

export interface PersonaCompileResponse {
  dense: string;
  structured: Record<string, unknown>;
  debug: string;
}
