import { afterEach, describe, expect, it, vi } from 'vitest'
import { askQuestion, getReadiness } from '../src/api'

const success = {
  answer: 'Three groups.',
  sql: 'SELECT TRT01P FROM adsl LIMIT 100',
  columns: ['TRT01P'],
  rows: [['Placebo']],
  row_count: 1,
  warnings: [],
}

const readiness = {
  status: 'ready',
  components: {
    backend: { status: 'ready', code: 'backend_ready', message: 'Backend is ready.' },
    database: { status: 'ready', code: 'database_ready', message: 'Database is ready.' },
    model: { status: 'ready', code: 'model_ready', message: 'Model is ready.' },
  },
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
})

describe('API URLs', () => {
  it('uses relative URLs when the API base URL is blank', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '   ')
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(readiness), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(success), { status: 200 }))

    await getReadiness()
    await askQuestion('question')

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/ready', undefined)
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/query', expect.any(Object))
  })

  it('uses absolute URLs when the API base URL is configured', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://seqchat-api.example.com')
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(readiness), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(success), { status: 200 }))

    await getReadiness()
    await askQuestion('question')

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'https://seqchat-api.example.com/api/ready',
      undefined,
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'https://seqchat-api.example.com/api/query',
      expect.any(Object),
    )
  })

  it('removes trailing slashes from the configured API base URL', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://seqchat-api.example.com/')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(readiness), { status: 200 }),
    )

    await getReadiness()

    expect(fetchMock).toHaveBeenCalledWith(
      'https://seqchat-api.example.com/api/ready',
      undefined,
    )
  })
})

describe('query API handling', () => {
  it('classifies a rejected fetch as an unreachable backend', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('network secret'))
    await expect(askQuestion('question')).rejects.toThrow('Cannot reach the SeqChat backend.')
  })

  it('uses a safe fallback for an empty response body', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 502 }))
    await expect(askQuestion('question')).rejects.toThrow('SeqChat could not complete the request.')
  })

  it('uses a safe fallback for a non-JSON response body', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('<html>SENTINEL_PROXY_BODY</html>', { status: 502 }),
    )
    const caught = await askQuestion('question').catch((error: unknown) => error)
    expect(caught).toBeInstanceOf(Error)
    expect((caught as Error).message).toBe('SeqChat could not complete the request.')
    expect((caught as Error).message).not.toContain('SENTINEL_PROXY_BODY')
  })

  it('preserves a structured backend error message', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: 'provider_auth_error',
            message: 'The model provider rejected authentication or authorization',
            stage: 'generation',
          },
        }),
        { status: 502 },
      ),
    )
    await expect(askQuestion('question')).rejects.toThrow(
      'The model provider rejected authentication or authorization',
    )
  })

  it('returns a valid successful query response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(success), { status: 200 }),
    )
    await expect(askQuestion('question')).resolves.toEqual(success)
  })
})
