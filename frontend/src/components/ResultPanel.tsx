import type { ResearchResponse } from '@/api/research'
import { AnswerCard } from '@/components/AnswerCard'
import { ContextChunks } from '@/components/ContextChunks'
import { LoadingState } from '@/components/LoadingState'
import { RouteIndicator } from '@/components/RouteIndicator'
import { SourcesList } from '@/components/SourcesList'

interface ResultPanelProps {
  loading: boolean
  response: ResearchResponse | null
  error: string | null
}

export function ResultPanel({ loading, response, error }: ResultPanelProps) {
  if (loading) return <LoadingState />

  if (error) {
    return <div className="error-block">ERROR · {error}</div>
  }

  if (!response) return null

  return (
    <>
      <RouteIndicator route={response.route} />
      <AnswerCard answer={response.answer} />
      <SourcesList sources={response.sources} />
      <ContextChunks chunks={response.retrieved_context} />
    </>
  )
}
