/**
 * K3 wired shell.
 *
 * Two panels: a query panel that drives `GET /retrieve`, and a persona
 * selector that drives `GET /persona/list` + `POST /persona/compile`.
 * GitHub KV is intentionally NOT used here — pipeline data stays local.
 */

import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useBridge } from './hooks/useBridge';
import type {
  PersonaCompileResponse,
  PersonaListItem,
  RetrievalResponse,
} from './types';

type LoadState<T> =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; data: T }
  | { kind: 'error'; message: string };

function errorOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export function App(): JSX.Element {
  const bridge = useBridge();

  // ---- Query panel state -------------------------------------------------
  const [query, setQuery] = useState('');
  const [retrieve, setRetrieve] = useState<LoadState<RetrievalResponse>>({ kind: 'idle' });

  const onSubmit = useCallback(
    async (e: FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      const q = query.trim();
      if (!q) return;
      setRetrieve({ kind: 'loading' });
      try {
        const data = await bridge.retrieve(q);
        setRetrieve({ kind: 'ok', data });
      } catch (err) {
        setRetrieve({ kind: 'error', message: errorOf(err) });
      }
    },
    [bridge, query],
  );

  // ---- Persona panel state -----------------------------------------------
  const [personas, setPersonas] = useState<LoadState<PersonaListItem[]>>({ kind: 'idle' });
  const [character, setCharacter] = useState<string>('');
  const [domains, setDomains] = useState<string[]>([]);
  const [profile, setProfile] = useState<LoadState<PersonaCompileResponse>>({ kind: 'idle' });

  useEffect(() => {
    let cancelled = false;
    setPersonas({ kind: 'loading' });
    bridge
      .listPersonas()
      .then((data) => {
        if (!cancelled) setPersonas({ kind: 'ok', data });
      })
      .catch((err: unknown) => {
        if (!cancelled) setPersonas({ kind: 'error', message: errorOf(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [bridge]);

  const compile = useCallback(async () => {
    setProfile({ kind: 'loading' });
    try {
      const data = await bridge.compilePersona({
        character: character || null,
        domains,
      });
      setProfile({ kind: 'ok', data });
    } catch (err) {
      setProfile({ kind: 'error', message: errorOf(err) });
    }
  }, [bridge, character, domains]);

  const toggleDomain = useCallback((id: string) => {
    setDomains((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  }, []);

  const characterOptions =
    personas.kind === 'ok' ? personas.data.filter((p) => p.kind === 'character') : [];
  const domainOptions =
    personas.kind === 'ok' ? personas.data.filter((p) => p.kind === 'domain') : [];

  // ---- Render ------------------------------------------------------------
  return (
    <main
      style={{
        fontFamily: 'system-ui, sans-serif',
        maxWidth: 760,
        margin: '2rem auto',
        padding: '0 1rem',
        lineHeight: 1.5,
      }}
    >
      <header>
        <h1>llm-rag-wiki</h1>
        <p style={{ color: '#555' }}>
          Local-first wiki + RAG + persona micro-app. All data stays on your machine
          (ADR-0003).
        </p>
      </header>

      <section aria-labelledby="query-heading" style={{ marginTop: '2rem' }}>
        <h2 id="query-heading">Query</h2>
        <form onSubmit={onSubmit}>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask the local wiki…"
            style={{ width: '100%', padding: '0.5rem' }}
            aria-label="Query"
          />
          <button
            type="submit"
            disabled={retrieve.kind === 'loading' || !query.trim()}
            style={{ marginTop: '0.5rem', padding: '0.5rem 1rem' }}
          >
            {retrieve.kind === 'loading' ? 'Searching…' : 'Search'}
          </button>
        </form>
        <RetrieveView state={retrieve} />
      </section>

      <section aria-labelledby="persona-heading" style={{ marginTop: '2.5rem' }}>
        <h2 id="persona-heading">Persona</h2>
        {personas.kind === 'loading' && <p>Loading personas…</p>}
        {personas.kind === 'error' && (
          <p style={{ color: '#a00' }}>Failed to load personas: {personas.message}</p>
        )}
        {personas.kind === 'ok' && (
          <>
            <label style={{ display: 'block', marginBottom: '0.5rem' }}>
              Character:
              <select
                value={character}
                onChange={(e) => setCharacter(e.target.value)}
                style={{ marginLeft: '0.5rem', padding: '0.25rem' }}
              >
                <option value="">(none)</option>
                {characterOptions.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.id})
                  </option>
                ))}
              </select>
            </label>
            <fieldset style={{ border: '1px solid #ddd', padding: '0.5rem' }}>
              <legend>Domains</legend>
              {domainOptions.length === 0 && (
                <span style={{ color: '#888' }}>No domain personas available.</span>
              )}
              {domainOptions.map((p) => (
                <label key={p.id} style={{ display: 'block' }}>
                  <input
                    type="checkbox"
                    checked={domains.includes(p.id)}
                    onChange={() => toggleDomain(p.id)}
                  />{' '}
                  {p.name} ({p.id})
                </label>
              ))}
            </fieldset>
            <button
              type="button"
              onClick={compile}
              disabled={profile.kind === 'loading'}
              style={{ marginTop: '0.5rem', padding: '0.5rem 1rem' }}
            >
              {profile.kind === 'loading' ? 'Compiling…' : 'Compile profile'}
            </button>
          </>
        )}
        <ProfileView state={profile} />
      </section>
    </main>
  );
}

function RetrieveView({ state }: { state: LoadState<RetrievalResponse> }): JSX.Element | null {
  if (state.kind === 'idle') return null;
  if (state.kind === 'loading') return <p>Searching…</p>;
  if (state.kind === 'error') return <p style={{ color: '#a00' }}>Error: {state.message}</p>;

  const { data } = state;
  if (data.status !== 'ok') {
    return (
      <div
        style={{
          marginTop: '1rem',
          padding: '0.75rem',
          background: '#fff8e0',
          border: '1px solid #e6c200',
        }}
      >
        <strong>{data.status}</strong>
        {data.error_code && <code style={{ marginLeft: '0.5rem' }}>{data.error_code}</code>}
        {data.message && <p style={{ margin: '0.25rem 0 0' }}>{data.message}</p>}
        {data.degradation_meta && (
          <pre style={{ fontSize: '0.8rem', overflowX: 'auto' }}>
            {JSON.stringify(data.degradation_meta, null, 2)}
          </pre>
        )}
      </div>
    );
  }
  return (
    <ol style={{ marginTop: '1rem', paddingLeft: '1.25rem' }}>
      {data.results.map((r) => (
        <li key={r.chunk_id} style={{ marginBottom: '1rem' }}>
          <div style={{ fontSize: '0.8rem', color: '#666' }}>
            score {r.score.toFixed(3)} · <code>{r.source}</code> · {r.heading}
          </div>
          <div>{r.excerpt}</div>
        </li>
      ))}
      {data.results.length === 0 && <li style={{ color: '#888' }}>No results.</li>}
    </ol>
  );
}

function ProfileView({ state }: { state: LoadState<PersonaCompileResponse> }): JSX.Element | null {
  if (state.kind === 'idle') return null;
  if (state.kind === 'loading') return <p>Compiling…</p>;
  if (state.kind === 'error') return <p style={{ color: '#a00' }}>Error: {state.message}</p>;
  return (
    <div style={{ marginTop: '1rem' }}>
      <h3 style={{ marginBottom: '0.25rem' }}>Compiled profile</h3>
      <pre
        style={{
          fontSize: '0.8rem',
          background: '#f6f6f6',
          padding: '0.5rem',
          overflowX: 'auto',
        }}
      >
        {state.data.dense}
      </pre>
      <details>
        <summary>Debug (YAML)</summary>
        <pre style={{ fontSize: '0.8rem', overflowX: 'auto' }}>{state.data.debug}</pre>
      </details>
    </div>
  );
}
