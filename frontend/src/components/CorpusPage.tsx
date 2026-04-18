import { useEffect, useRef, useState } from 'react'
import { listDocuments, ingestDocument, type Document } from '@/api/corpus'

export function CorpusPage() {
  const [docs, setDocs] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [title, setTitle] = useState('')
  const [url, setUrl] = useState('')
  const [content, setContent] = useState('')
  const [ingesting, setIngesting] = useState(false)
  const [ingestMsg, setIngestMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const fileRef = useRef<HTMLInputElement>(null)

  async function fetchDocs() {
    setLoading(true)
    setError(null)
    try {
      setDocs(await listDocuments())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchDocs() }, [])

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    if (!title) setTitle(file.name.replace(/\.[^.]+$/, ''))
    if (file.name.toLowerCase().endsWith('.pdf')) {
      setContent('Extracting PDF text…')
      const form = new FormData()
      form.append('file', file)
      try {
        const res = await fetch('/api/corpus/upload', { method: 'POST', body: form })
        if (!res.ok) {
          const err = await res.json().catch(() => ({}))
          setContent('')
          setIngestMsg({ ok: false, text: err.detail ?? `PDF extraction failed (${res.status})` })
          return
        }
        const { text } = await res.json()
        setContent(text)
      } catch {
        setContent('')
        setIngestMsg({ ok: false, text: 'PDF extraction failed — is the server running?' })
      }
    } else {
      const reader = new FileReader()
      reader.onload = () => setContent(reader.result as string)
      reader.readAsText(file)
    }
  }

  async function handleIngest(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim() || !content.trim() || !url.trim()) return
    setIngesting(true)
    setIngestMsg(null)
    try {
      const result = await ingestDocument({ title, content, url })
      setIngestMsg({ ok: true, text: `Ingested "${result.title}" — ${result.chunks_stored} chunks` })
      setTitle(''); setUrl(''); setContent('')
      if (fileRef.current) fileRef.current.value = ''
      await fetchDocs()
    } catch (e) {
      setIngestMsg({ ok: false, text: (e as Error).message })
    } finally {
      setIngesting(false)
    }
  }

  return (
    <div className="corpus-page">
      <section className="corpus-section">
        <div className="section-label">ADD DOCUMENT</div>
        <form className="ingest-form" onSubmit={handleIngest}>
          <div className="ingest-row">
            <input
              className="ingest-input"
              placeholder="Title"
              value={title}
              onChange={e => setTitle(e.target.value)}
              disabled={ingesting}
              required
            />
            <input
              className="ingest-input"
              placeholder="URL / source"
              value={url}
              onChange={e => setUrl(e.target.value)}
              disabled={ingesting}
              required
            />
          </div>
          <div className="ingest-file-row">
            <label className="file-label">
              <span>UPLOAD FILE</span>
              <input
                ref={fileRef}
                type="file"
                accept=".txt,.md,.pdf"
                onChange={handleFile}
                disabled={ingesting}
                style={{ display: 'none' }}
              />
            </label>
            <span className="ingest-hint">or paste text below</span>
          </div>
          <textarea
            className="ingest-textarea"
            placeholder="Paste document text…"
            value={content}
            onChange={e => setContent(e.target.value)}
            disabled={ingesting}
            rows={6}
            required
          />
          <div className="ingest-footer">
            {ingestMsg && (
              <span className={ingestMsg.ok ? 'ingest-ok' : 'ingest-err'}>
                {ingestMsg.text}
              </span>
            )}
            <button className="submit-btn" type="submit" disabled={ingesting}>
              {ingesting ? 'INGESTING…' : 'INGEST →'}
            </button>
          </div>
        </form>
      </section>

      <section className="corpus-section">
        <div className="section-label">
          CORPUS
          <span style={{ color: 'var(--text-dimmer)', fontWeight: 300, fontSize: '9px', letterSpacing: '0.06em' }}>
            {loading ? '…' : `${docs.length} DOCUMENT${docs.length !== 1 ? 'S' : ''}`}
          </span>
          <button className="refresh-btn" onClick={fetchDocs} disabled={loading}>↻</button>
        </div>

        {error && <div className="error-block">{error}</div>}

        {!loading && docs.length === 0 && !error && (
          <p className="sources-empty">No documents in corpus yet.</p>
        )}

        {docs.length > 0 && (
          <table className="corpus-table">
            <thead>
              <tr>
                <th>TITLE</th>
                <th>URL</th>
                <th>CHUNKS</th>
              </tr>
            </thead>
            <tbody>
              {docs.map(doc => (
                <tr key={doc.document_id}>
                  <td>{doc.title}</td>
                  <td>
                    <a href={doc.url} target="_blank" rel="noreferrer" className="sources-link">
                      {doc.url}
                    </a>
                  </td>
                  <td className="chunks-cell">{doc.chunk_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
