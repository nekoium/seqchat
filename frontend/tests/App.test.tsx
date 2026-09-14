import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../src/App'

const success = {
  answer: 'High Dose 84, Low Dose 84, and Placebo 86.',
  sql: 'SELECT TRT01P, COUNT(*) FROM adsl GROUP BY TRT01P LIMIT 100',
  columns: ['TRT01P', 'subject_count'],
  rows: [
    ['Xanomeline High Dose', 84],
    ['Xanomeline Low Dose', 84],
    ['Placebo', 86],
  ],
  row_count: 3,
  warnings: [],
}

const ready = {
  status: 'ready',
  components: {
    backend: { status: 'ready', code: 'backend_reachable', message: 'API ready.' },
    database: { status: 'ready', code: 'database_ready', message: 'Database ready.' },
    model: { status: 'ready', code: 'model_configured', message: 'Model configured.' },
  },
}

function jsonResponse(value: object, status = 200): Response {
  return new Response(JSON.stringify(value), { status })
}

function mockReadyThen(response: Response | Promise<Response>): void {
  vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(jsonResponse(ready))
    .mockImplementationOnce(() => Promise.resolve(response))
}

afterEach(() => vi.restoreAllMocks())

describe('SeqChat', () => {
  it('shows ready state on initial page load', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(ready))
    render(<App />)
    expect(await screen.findByLabelText('SeqChat readiness')).toHaveTextContent('Ready.')
  })

  it('shows dataset initialization guidance', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({
      ...ready,
      status: 'not_ready',
      components: {
        ...ready.components,
        database: {
          status: 'not_ready',
          code: 'database_not_ready',
          message: 'Initialize the SeqChat dataset before submitting a query.',
        },
      },
    }))
    render(<App />)
    expect(await screen.findByLabelText('SeqChat readiness')).toHaveTextContent(
      'Initialize the SeqChat dataset',
    )
  })

  it('shows missing model configuration guidance', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({
      ...ready,
      status: 'not_ready',
      components: {
        ...ready.components,
        model: {
          status: 'not_ready',
          code: 'model_not_configured',
          message: 'Configure the SeqChat model provider before submitting a query.',
        },
      },
    }))
    render(<App />)
    expect(await screen.findByLabelText('SeqChat readiness')).toHaveTextContent(
      'Configure the SeqChat model provider',
    )
  })

  it('shows invalid model configuration guidance', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({
      ...ready,
      status: 'not_ready',
      components: {
        ...ready.components,
        model: {
          status: 'not_ready',
          code: 'model_configuration_invalid',
          message: 'Correct the SeqChat model provider configuration.',
        },
      },
    }))
    render(<App />)
    expect(await screen.findByLabelText('SeqChat readiness')).toHaveTextContent(
      'Correct the SeqChat model provider configuration',
    )
  })

  it('shows backend and proxy guidance when readiness fetch is unreachable', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('offline'))
    render(<App />)
    const readiness = await screen.findByLabelText('SeqChat readiness')
    expect(readiness).toHaveTextContent('Backend unreachable.')
    expect(readiness).toHaveTextContent('Start FastAPI and check the Vite proxy.')
  })

  it('shows loading feedback while the query request is pending', async () => {
    mockReadyThen(new Promise<Response>(() => undefined))
    render(<App />)
    await screen.findByText('Ready.')
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(screen.getByRole('status')).toHaveTextContent('Inspecting the schema')
    expect(screen.getByRole('button', { name: 'Analyzing…' })).toBeDisabled()
  })

  it('renders the answer, SQL, and result evidence', async () => {
    mockReadyThen(jsonResponse(success))
    render(<App />)
    await screen.findByText('Ready.')
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText(success.answer)).toBeVisible()
    expect(screen.getByText(success.sql)).toBeVisible()
    expect(screen.getByRole('cell', { name: 'Placebo' })).toBeVisible()
    expect(screen.getByRole('cell', { name: '86' })).toBeVisible()
  })

  it('renders a query error separately and leaves the form usable', async () => {
    mockReadyThen(jsonResponse(
      { error: { code: 'provider_error', message: 'The model is unavailable', stage: 'generation' } },
      502,
    ))
    render(<App />)
    await screen.findByText('Ready.')
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The model is unavailable')
    expect(screen.getByLabelText('SeqChat readiness')).toHaveTextContent('Ready.')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Ask' })).toBeEnabled())
  })
})
