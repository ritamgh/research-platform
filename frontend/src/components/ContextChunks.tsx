import { useState } from 'react'

const PREVIEW = 280

function Chunk({ text, index }: { text: string; index: number }) {
  const [open, setOpen] = useState(false)
  const truncated = text.length > PREVIEW

  return (
    <div className="chunk-item">
      <button className="chunk-trigger" onClick={() => setOpen(!open)}>
        <span className={`chunk-arrow${open ? ' open' : ''}`}>▸</span>
        <span className="chunk-idx">{String(index + 1).padStart(2, '0')}</span>
        <span className="chunk-text">
          {open || !truncated ? text : `${text.slice(0, PREVIEW)}…`}
        </span>
      </button>
    </div>
  )
}

interface ContextChunksProps {
  chunks: string[]
}

export function ContextChunks({ chunks }: ContextChunksProps) {
  if (chunks.length === 0) return null
  return (
    <div className="context-section">
      <div className="section-label dimmed">
        AGENT RESPONSES
        <span style={{ color: 'var(--text-dimmer)', fontWeight: 300, letterSpacing: '0.06em', fontSize: '9px' }}>
          {chunks.length} CHUNK{chunks.length !== 1 ? 'S' : ''}
        </span>
      </div>
      {chunks.map((chunk, i) => (
        <Chunk key={i} text={chunk} index={i} />
      ))}
    </div>
  )
}
