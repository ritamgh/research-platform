export function LoadingState() {
  return (
    <div className="loading-wrap">
      <div className="loading-label">
        ANALYZING
        <span className="loading-dots">
          <span>·</span>
          <span>·</span>
          <span>·</span>
        </span>
      </div>
      <div className="loading-bar" />
      <div className="loading-line w-full" style={{ height: '12px', background: 'var(--surface)', borderRadius: '1px', marginBottom: '0.5rem' }} />
      <div className="loading-line w-90"  style={{ height: '12px', background: 'var(--surface)', borderRadius: '1px', marginBottom: '0.5rem' }} />
      <div className="loading-line w-75"  style={{ height: '12px', background: 'var(--surface)', borderRadius: '1px', marginBottom: '0.5rem' }} />
      <div className="loading-line w-85"  style={{ height: '12px', background: 'var(--surface)', borderRadius: '1px', marginBottom: '0.5rem' }} />
      <div className="loading-line w-60"  style={{ height: '12px', background: 'var(--surface)', borderRadius: '1px', marginBottom: '2rem' }} />
      <div className="loading-line w-40"  style={{ height: '1px', background: 'var(--border)', marginBottom: '0.5rem' }} />
      <div className="loading-line w-90"  style={{ height: '1px', background: 'var(--border)', marginBottom: '0.5rem' }} />
    </div>
  )
}
