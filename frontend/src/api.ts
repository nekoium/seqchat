export interface QueryResult {
  answer: string
  sql: string
  columns: string[]
  rows: unknown[][]
  row_count: number
  warnings: string[]
}

interface ErrorPayload {
  error?: {
    code?: string
    message?: string
    stage?: string
  }
}

export async function askQuestion(question: string): Promise<QueryResult> {
  const response = await fetch('/api/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  const payload = (await response.json()) as QueryResult | ErrorPayload
  if (!response.ok) {
    const error = (payload as ErrorPayload).error
    throw new Error(error?.message ?? 'SeqChat could not complete the request.')
  }
  return payload as QueryResult
}
