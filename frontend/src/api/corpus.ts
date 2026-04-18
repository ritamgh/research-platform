export interface Document {
  document_id: string
  title: string
  url: string
  chunk_count: number
}

export interface IngestRequest {
  title: string
  content: string
  url: string
  collection?: string
}

export interface IngestResult {
  document_id: string
  title: string
  chunks_stored: number
  collection: string
}

export async function listDocuments(collection = 'documents'): Promise<Document[]> {
  const res = await fetch(`/api/corpus?collection=${encodeURIComponent(collection)}`)
  if (!res.ok) throw new Error(`Failed to fetch corpus (${res.status})`)
  const data = await res.json()
  return data.documents as Document[]
}

export async function ingestDocument(req: IngestRequest): Promise<IngestResult> {
  const res = await fetch('/api/corpus', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ collection: 'documents', ...req }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? `Ingest failed (${res.status})`)
  }
  return res.json()
}
