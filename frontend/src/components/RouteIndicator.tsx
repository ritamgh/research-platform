const ROUTE_META: Record<string, { label: string; pip: string }> = {
  web_only: { label: 'WEB RESEARCH',    pip: 'web'    },
  rag_only: { label: 'RAG LOOKUP',      pip: 'rag'    },
  both:     { label: 'WEB + RAG',       pip: 'both'   },
  direct:   { label: 'DIRECT ANSWER',   pip: 'direct' },
  adk:      { label: 'ADK COORDINATOR', pip: 'adk'    },
}

interface RouteIndicatorProps {
  route: string
}

export function RouteIndicator({ route }: RouteIndicatorProps) {
  const meta = ROUTE_META[route] ?? { label: route.toUpperCase(), pip: 'direct' }
  return (
    <div className="route-row">
      <span className={`route-pip ${meta.pip}`} />
      <span className="route-label">{meta.label}</span>
      <span>·</span>
      <span>ANSWERED</span>
    </div>
  )
}
