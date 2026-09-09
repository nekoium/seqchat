import { FormEvent, useState } from 'react'
import { askQuestion, type QueryResult } from './api'
import './styles.css'

const GOLDEN_QUESTION = 'How many subjects are in each planned treatment group?'

export default function App() {
  const [question, setQuestion] = useState(GOLDEN_QUESTION)
  const [result, setResult] = useState<QueryResult | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!question.trim() || loading) return
    setLoading(true)
    setError('')
    try {
      setResult(await askQuestion(question.trim()))
    } catch (caught) {
      setResult(null)
      setError(caught instanceof Error ? caught.message : 'SeqChat could not complete the request.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main>
      <header>
        <p className="eyebrow">CDISC pilot data · ADSL</p>
        <h1>Ask the dataset</h1>
        <p className="lede">SeqChat turns one question into validated SQL and shows the evidence behind its answer.</p>
      </header>

      <form onSubmit={submit} aria-label="Ask SeqChat">
        <label htmlFor="question">Question</label>
        <div className="input-row">
          <input
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            maxLength={2000}
            disabled={loading}
          />
          <button type="submit" disabled={loading || !question.trim()}>
            {loading ? 'Analyzing…' : 'Ask'}
          </button>
        </div>
      </form>

      {error && <div className="error" role="alert"><strong>Request failed.</strong> {error}</div>}
      {loading && <p className="status" role="status">Inspecting the schema and querying DuckDB…</p>}

      {!loading && !error && !result && (
        <section className="empty"><p>Your answer, generated SQL, and returned rows will appear here.</p></section>
      )}

      {result && (
        <div className="evidence-grid">
          <section className="answer" aria-labelledby="answer-title">
            <p className="section-label">Grounded answer</p>
            <h2 id="answer-title">Result</h2>
            <p>{result.answer}</p>
            {result.warnings.map((warning) => <p className="warning" key={warning}>{warning}</p>)}
          </section>

          <section aria-labelledby="sql-title">
            <p className="section-label">Executed query</p>
            <h2 id="sql-title">SQL</h2>
            <pre><code>{result.sql}</code></pre>
          </section>

          <section className="table-section" aria-labelledby="rows-title">
            <p className="section-label">Database evidence · {result.row_count} rows</p>
            <h2 id="rows-title">Returned rows</h2>
            {result.rows.length === 0 ? (
              <p>No rows matched this question.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead><tr>{result.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
                  <tbody>
                    {result.rows.map((row, rowIndex) => (
                      <tr key={rowIndex}>
                        {row.map((value, columnIndex) => <td key={`${rowIndex}-${result.columns[columnIndex]}`}>{String(value ?? '')}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </main>
  )
}
