interface SourcesListProps {
  sources: string[]
}

export function SourcesList({ sources }: SourcesListProps) {
  return (
    <div className="sources-section">
      <div className="section-label dimmed">SOURCES</div>
      {sources.length === 0 ? (
        <p className="sources-empty">No sources extracted.</p>
      ) : (
        <ul className="sources-list">
          {sources.map((src, i) => (
            <li key={i} className="sources-item">
              <span className="sources-num">{String(i + 1).padStart(2, '0')}</span>
              {/^https?:\/\//.test(src) ? (
                <a href={src} target="_blank" rel="noopener noreferrer" className="sources-link">
                  {src}
                </a>
              ) : (
                <span className="sources-link">{src}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
