import { afterEach, describe, expect, it, vi } from 'vitest'
import { askQuestion } from '../src/api'

const success = {
  answer: 'Three groups.',
  sql: 'SELECT TRT01P FROM adsl LIMIT 100',
  columns: ['TRT01P'],
  rows: [['Placebo']],
  row_count: 1,
  warnings: [],
}

afterEach(() => vi.restoreAllMocks())

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
