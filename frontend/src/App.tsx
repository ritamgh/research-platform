import { useState } from 'react'
import { research, type ResearchResponse, type ResearchError } from '@/api/research'
import { CorpusPage } from '@/components/CorpusPage'
import { SearchBar } from '@/components/SearchBar'
import { ResultPanel } from '@/components/ResultPanel'

type Tab = 'research' | 'corpus'

export default function App() {
  const [tab, setTab] = useState<Tab>('research')
  const [query, setQuery] = useState('')
  const [response, setResponse] = useState<ResearchResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(q: string) {
    if (!q.trim()) return
    setLoading(true)
    setError(null)
    setResponse(null)
    try {
      const result = await research(q.trim())
      setResponse(result)
    } catch (err) {
      const e = err as ResearchError
      setError(e.message ?? 'An unexpected error occurred.')
    } finally {
      setLoading(false)
    }
  }

  const hasResult = loading || !!response || !!error

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="header-brand">
          <span className="brand-name">RESEARCH</span>
          <span className="brand-sep">·</span>
          <span className="brand-sub">PLATFORM</span>
        </div>
        <nav className="app-nav">
          <button
            className={`nav-tab${tab === 'research' ? ' active' : ''}`}
            onClick={() => setTab('research')}
          >RESEARCH</button>
          <button
            className={`nav-tab${tab === 'corpus' ? ' active' : ''}`}
            onClick={() => setTab('corpus')}
          >CORPUS</button>
        </nav>
        <div className="header-meta">
          <span className="version-tag">v2.0.0</span>
          <span className="live-dot" />
        </div>
      </header>

      <main className="app-main">
        {tab === 'research' && (
          <>
            <section className="query-section">
              <div className="section-label">QUERY</div>
              <SearchBar
                query={query}
                loading={loading}
                onChange={setQuery}
                onSubmit={handleSubmit}
              />
            </section>

            {hasResult && (
              <section className="result-section">
                <ResultPanel loading={loading} response={response} error={error} />
              </section>
            )}
          </>
        )}

        {tab === 'corpus' && <CorpusPage />}
      </main>
    </div>
  )
}
