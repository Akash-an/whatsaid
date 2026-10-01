import React, { useState, useRef, useCallback } from 'react';
import { Send, RotateCcw, AlertCircle, Copy, Check, ChevronDown } from 'lucide-react';
import './Ask.css';

import logger from '../lib/logger';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EXAMPLE_QUERIES = [
  'Who shared the most links?',
  'Show all YouTube links pending review',
  'How many messages were sent in June?',
];

const URL_RE = /^https?:\/\//i;

// ---------------------------------------------------------------------------
// Copy-to-clipboard hook
// ---------------------------------------------------------------------------

/**
 * Returns [copied, handleCopy].
 * handleCopy(columns, rows) serialises the table as TSV and writes it to the
 * clipboard. `copied` is true for 2 s after a successful copy, so the button
 * can show a ✓ confirmation state.
 */
function useCopyTable() {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback((columns, rows) => {
    const header = columns.join('\t');
    const body = rows
      .map((row) => row.map((cell) => (cell === null || cell === undefined ? '' : String(cell))).join('\t'))
      .join('\n');
    const tsv = `${header}\n${body}`;

    navigator.clipboard.writeText(tsv).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, []);

  return [copied, handleCopy];
}

function CopyButton({ columns, rows }) {
  const [copied, handleCopy] = useCopyTable();

  return (
    <button
      className={`ask-copy-btn ${copied ? 'ask-copy-btn--success' : ''}`}
      onClick={() => handleCopy(columns, rows)}
      title="Copy table as TSV (paste into Excel or Google Sheets)"
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
      {copied ? 'Copied!' : 'Copy'}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Render a single table cell value.  URLs are turned into links; null/undefined
 * are shown as a muted "—" placeholder.
 */
function CellValue({ value }) {
  if (value === null || value === undefined || value === '') {
    return <span className="ask-cell-null">—</span>;
  }
  const str = String(value);
  if (URL_RE.test(str)) {
    return (
      <a href={str} target="_blank" rel="noopener noreferrer">
        {str.length > 60 ? str.slice(0, 57) + '…' : str}
      </a>
    );
  }
  return <>{str}</>;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ThinkingIndicator() {
  return (
    <div className="ask-thinking">
      <div className="ask-thinking-dot" />
      <div className="ask-thinking-dot" />
      <div className="ask-thinking-dot" />
      <span>Generating query…</span>
    </div>
  );
}

function SkeletonLoader() {
  return (
    <div className="ask-skeleton glass-panel">
      <div className="skeleton-line" />
      <div className="skeleton-line" />
      <div className="skeleton-line" />
      <div className="skeleton-line" />
    </div>
  );
}

function SqlDisclosure({ sql }) {
  return (
    <details className="ask-sql-disclosure" open>
      <summary>
        <ChevronDown size={14} />
        Generated SQL
      </summary>
      <pre className="ask-sql-pre">{sql}</pre>
    </details>
  );
}

function ResultTable({ columns, rows }) {
  if (rows.length === 0) {
    return (
      <div className="ask-empty-state glass-panel">
        <span>No rows matched your query.</span>
      </div>
    );
  }

  return (
    <div className="ask-table-wrapper glass-panel">
      <table className="ask-table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            // Using row index as key is intentional — rows have no stable id here.
            // eslint-disable-next-line react/no-array-index-key
            <tr key={ri}>
              {row.map((cell, ci) => (
                // eslint-disable-next-line react/no-array-index-key
                <td key={ci}>
                  <CellValue value={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export default function Ask() {
  const [question, setQuestion] = useState('');
  const [status, setStatus] = useState('idle'); // 'idle' | 'loading' | 'result' | 'error'
  const [result, setResult] = useState(null);   // NLQueryResponse
  const [error, setError] = useState(null);

  const textareaRef = useRef(null);

  // ---- Query execution ------------------------------------------------

  const runQuery = useCallback(async (q, page = 1) => {
    const trimmed = (q || question).trim();
    if (!trimmed) return;

    logger.info('ask:query', 'NL query submitted', { question: trimmed.slice(0, 200), page });
    setStatus('loading');
    setError(null);

    const start = performance.now();
    try {
      logger.debug('ask:fetch', 'Fetch started', { url: '/api/query', payload: { question: trimmed, page } });
      const res = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: trimmed, page }),
      });

      const durationMs = Math.round(performance.now() - start);
      logger.debug('ask:fetch', 'Fetch response received', { status: res.status, durationMs });
      
      const text = await res.text();
      let data;
      try {
          data = JSON.parse(text);
      } catch (e) {
          logger.error('ask:fetch', 'JSON parse error on response', { raw: text.slice(0, 200) });
          throw new Error('Invalid JSON response from server');
      }

      if (!res.ok) {
        logger.warn('ask:fetch', 'Server returned non-OK', { status: res.status, detail: data.detail });
        throw new Error(data.detail || `Server error ${res.status}`);
      }

      setResult(data);
      setStatus('result');
      logger.debug('ask:render', 'Result rendered', { rowCount: data.row_count, totalCount: data.total_count });
    } catch (err) {
      logger.error('ask:fetch', 'Query failed', { error: err.message });
      setError(err.message);
      setStatus('error');
    }
  }, [question]);

  // ---- Event handlers -------------------------------------------------

  const handleSubmit = (e) => {
    e.preventDefault();
    runQuery(question, 1);
  };

  const handleKeyDown = (e) => {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      runQuery(question, 1);
    }
  };

  const handleChip = (q) => {
    setQuestion(q);
    runQuery(q, 1);
  };

  const handleReset = () => {
    logger.debug('ask:reset', 'Resetting query state');
    setStatus('idle');
    setResult(null);
    setError(null);
    setQuestion('');
    setTimeout(() => textareaRef.current?.focus(), 50);
  };

  const handlePageChange = (newPage) => {
    runQuery(question, newPage);
  };

  // ---- Render ---------------------------------------------------------

  const isIdle    = status === 'idle';
  const isLoading = status === 'loading';
  const isResult  = status === 'result';
  const isError   = status === 'error';

  return (
    <div className="ask-container fade-in">

      {/* Hero header — only shown in idle state */}
      {isIdle && (
        <div className="ask-hero">
          <h2>Ask Your Data</h2>
          <p>Ask anything about your chat data in plain English</p>
        </div>
      )}

      {/* Query input */}
      <div className="ask-input-section">
        <form onSubmit={handleSubmit}>
          <div className="ask-textarea-wrapper">
            <div className="ask-input-row">
              <textarea
                ref={textareaRef}
                className="ask-textarea"
                rows={2}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="e.g. Who shared the most links? or Show all YouTube links pending review…"
                disabled={isLoading}
                autoFocus
              />
              <button
                type="submit"
                className="ask-submit-btn"
                disabled={isLoading || !question.trim()}
              >
                <Send size={16} />
                Ask
              </button>
            </div>
          </div>
        </form>

        {/* Example chips — only in idle state */}
        {isIdle && (
          <div className="ask-chips">
            {EXAMPLE_QUERIES.map((q) => (
              <button key={q} className="ask-chip" onClick={() => handleChip(q)}>
                {q}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Loading state */}
      {isLoading && (
        <>
          <ThinkingIndicator />
          <SkeletonLoader />
        </>
      )}

      {/* Error state */}
      {isError && (
        <div className="ask-error-banner">
          <AlertCircle size={18} style={{ flexShrink: 0, marginTop: 1 }} />
          <div>
            <strong>Query failed</strong>
            <p style={{ marginTop: '0.25rem', color: 'inherit' }}>{error}</p>
          </div>
        </div>
      )}

      {/* Results state */}
      {isResult && result && (
        <div className="ask-results">

          {/* Generated SQL */}
          <SqlDisclosure sql={result.sql} />

          {/* Summary bar */}
          <div className="ask-summary-bar">
            <span className="ask-result-count">
              Showing{' '}
              <strong>{result.row_count}</strong> of{' '}
              <strong>{result.total_count.toLocaleString()}</strong> result
              {result.total_count !== 1 ? 's' : ''}
              {result.total_pages > 1 && (
                <> — page <strong>{result.page}</strong> of <strong>{result.total_pages}</strong></>
              )}
            </span>
            <div className="ask-summary-actions">
              <CopyButton columns={result.columns} rows={result.rows} />
              <button className="ask-new-query-btn" onClick={handleReset}>
                <RotateCcw size={13} style={{ marginRight: '0.35rem' }} />
                New Query
              </button>
            </div>
          </div>

          {/* Data table */}
          <ResultTable columns={result.columns} rows={result.rows} />

          {/* Pagination */}
          {result.total_pages > 1 && (
            <div className="ask-pagination">
              <button
                disabled={result.page <= 1}
                onClick={() => handlePageChange(result.page - 1)}
              >
                ← Previous
              </button>
              <span className="ask-page-info">
                Page {result.page} of {result.total_pages}
              </span>
              <button
                disabled={result.page >= result.total_pages}
                onClick={() => handlePageChange(result.page + 1)}
              >
                Next →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
