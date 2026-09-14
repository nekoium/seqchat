export interface QueryResult {
  answer: string
  sql: string
  columns: string[]
  rows: unknown[][]
  row_count: number
  warnings: string[]
}

export interface ReadinessComponent {
  status: 'ready' | 'not_ready'
  code: string
  message: string
}

export interface ReadinessResult {
  status: 'ready' | 'not_ready'
  components: {
    backend: ReadinessComponent
    database: ReadinessComponent
    model: ReadinessComponent
  }
}

interface ErrorPayload {
  error?: {
    code?: string
    message?: string
    stage?: string
  }
}

function apiUrl(path: `/api/${string}`): string {
  const baseUrl = import.meta.env.VITE_API_BASE_URL?.trim()
  return baseUrl ? `${baseUrl.replace(/\/+$/, '')}${path}` : path
}

async function fetchOrBackendError(input: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init)
  } catch {
    throw new Error('Cannot reach the SeqChat backend.')
  }
}

async function parseJson(response: Response): Promise<unknown | null> {
  try {
    const text = await response.text()
    if (!text.trim()) return null
    return JSON.parse(text) as unknown
  } catch {
    return null
  }
}

function structuredError(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null
  const error = (payload as ErrorPayload).error
  return error
    && typeof error.code === 'string' && !!error.code.trim()
    && typeof error.message === 'string' && !!error.message.trim()
    && typeof error.stage === 'string' && !!error.stage.trim()
    ? error.message
    : null
}

function isQueryResult(payload: unknown): payload is QueryResult {
  if (!payload || typeof payload !== 'object') return false
  const value = payload as Partial<QueryResult>
  return typeof value.answer === 'string'
    && typeof value.sql === 'string'
    && Array.isArray(value.columns)
    && value.columns.every((column) => typeof column === 'string')
    && Array.isArray(value.rows)
    && value.rows.every(Array.isArray)
    && typeof value.row_count === 'number'
    && Array.isArray(value.warnings)
    && value.warnings.every((warning) => typeof warning === 'string')
}

function isReadiness(payload: unknown): payload is ReadinessResult {
  if (!payload || typeof payload !== 'object') return false
  const value = payload as Partial<ReadinessResult>
  const components = value.components
  return (value.status === 'ready' || value.status === 'not_ready')
    && !!components
    && ['backend', 'database', 'model'].every((name) => {
      const component = components[name as keyof typeof components]
      return !!component
        && (component.status === 'ready' || component.status === 'not_ready')
        && typeof component.code === 'string'
        && typeof component.message === 'string'
    })
}

export async function askQuestion(question: string): Promise<QueryResult> {
  const response = await fetchOrBackendError(apiUrl('/api/query'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  const payload = await parseJson(response)
  if (!response.ok) {
    throw new Error(structuredError(payload) ?? 'SeqChat could not complete the request.')
  }
  if (!isQueryResult(payload)) {
    throw new Error('SeqChat received an unreadable response from the backend.')
  }
  return payload
}

export async function getReadiness(): Promise<ReadinessResult> {
  const response = await fetchOrBackendError(apiUrl('/api/ready'))
  const payload = await parseJson(response)
  if (!response.ok || !isReadiness(payload)) {
    throw new Error('SeqChat could not read backend readiness.')
  }
  return payload
}
