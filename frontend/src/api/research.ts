export interface ResearchRequest {
  query: string
}

export interface ResearchResponse {
  answer: string
  sources: string[]
  route: string
  retrieved_context: string[]
}

export interface ResearchError {
  message: string
  status?: number
}

export async function research(query: string): Promise<ResearchResponse> {
  const response = await fetch('/api/research', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query } satisfies ResearchRequest),
  })

  if (!response.ok) {
    const status = response.status
    let message = `Request failed (${status})`
    if (status === 400) message = 'Query must not be empty.'
    else if (status === 504) message = 'Research timed out — the query may be too complex. Try again.'
    else if (status === 500) message = 'An internal error occurred. Please try again.'
    throw { message, status } satisfies ResearchError
  }

  return response.json() as Promise<ResearchResponse>
}
