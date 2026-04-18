import { type KeyboardEvent } from 'react'

interface SearchBarProps {
  query: string
  loading: boolean
  onChange: (value: string) => void
  onSubmit: (query: string) => void
}

export function SearchBar({ query, loading, onChange, onSubmit }: SearchBarProps) {
  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (query.trim() && !loading) onSubmit(query)
    }
  }

  return (
    <>
      <div className="query-input-wrap">
        <span className="query-prompt">›</span>
        <textarea
          className="query-textarea"
          value={query}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a research question…"
          disabled={loading}
          autoFocus
          rows={3}
        />
      </div>
      <div className="query-footer">
        <span className="query-hint">SHIFT+ENTER for new line</span>
        <button
          className="submit-btn"
          onClick={() => onSubmit(query)}
          disabled={!query.trim() || loading}
        >
          {loading ? 'ANALYZING' : 'SUBMIT →'}
        </button>
      </div>
    </>
  )
}
