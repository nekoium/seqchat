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

afterEach(() => vi.restoreAllMocks())

describe('SeqChat', () => {
  it('shows loading feedback while the request is pending', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => new Promise(() => undefined))
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(screen.getByRole('status')).toHaveTextContent('Inspecting the schema')
    expect(screen.getByRole('button', { name: 'Analyzing…' })).toBeDisabled()
  })

  it('renders the answer, SQL, and result evidence', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(success), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText(success.answer)).toBeVisible()
    expect(screen.getByText(success.sql)).toBeVisible()
    expect(screen.getByRole('cell', { name: 'Placebo' })).toBeVisible()
    expect(screen.getByRole('cell', { name: '86' })).toBeVisible()
  })

  it('renders a safe error and leaves the form usable', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ error: { code: 'provider_error', message: 'The model is unavailable', stage: 'generation' } }),
        { status: 502, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The model is unavailable')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Ask' })).toBeEnabled())
  })
})
