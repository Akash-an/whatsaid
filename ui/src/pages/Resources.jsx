import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Search, ChevronDown, ChevronUp, ExternalLink, Filter, Sparkles, RefreshCw, Loader, CalendarRange, X, Copy, Check } from 'lucide-react';
import './Resources.css';
import logger from '../lib/logger';

export default function Resources() {
  const [resources, setResources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Pagination & Filtering state
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [total, setTotal] = useState(0);
  
  const [search, setSearch] = useState('');
  const [platform, setPlatform] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  // Expanded row state
  const [expandedId, setExpandedId] = useState(null);

  // Enrichment state: Set of resource IDs currently being enriched
  const [enrichingIds, setEnrichingIds] = useState(new Set());
  // Ref to track active polling timers so we can clean them up
  const pollingTimers = useRef({});
  // Copy-to-clipboard feedback state
  const [copied, setCopied] = useState(false);
  // Enrich All state
  const [enrichingAll, setEnrichingAll] = useState(false);

  /**
   * Fetch ALL rows matching the current filters (single large request) and
   * copy them to the clipboard as a UTF-8 CSV string.
   *
   * Columns: Platform, Sender, URL, Title, Date, Tags, Notes
   */
  const handleCopyCSV = useCallback(async () => {
    logger.info('resources:csv', 'Copy CSV triggered', { search, platform, dateFrom, dateTo });
    try {
      const params = new URLSearchParams({ page: 1, page_size: 5000 });
      if (search)   params.append('search',    search);
      if (platform) params.append('platform',  platform);
      if (dateFrom) params.append('date_from', dateFrom);
      if (dateTo)   params.append('date_to',   dateTo);

      const res = await fetch(`/api/resources?${params.toString()}`);
      if (!res.ok) throw new Error('Failed to fetch resources for export');
      const { items } = await res.json();

      const escape = (v) => {
        if (v == null) return '';
        const s = String(v);
        // Wrap in quotes if the value contains a comma, quote, or newline
        return s.includes(',') || s.includes('"') || s.includes('\n')
          ? `"${s.replace(/"/g, '""')}"`
          : s;
      };

      const headers = ['Platform', 'Sender', 'URL', 'Title', 'Date', 'Tags', 'Notes'];
      const rows = items.map(r => [
        r.platform || '',
        r.sender   || '',
        r.canonical_url || r.original_url || '',
        r.title    || '',
        r.message_timestamp
          ? new Date(r.message_timestamp.replace(' ', 'T')).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
          : '',
        r.tags  || '',
        r.notes || '',
      ].map(escape).join(','));

      const csv = [headers.join(','), ...rows].join('\n');
      await navigator.clipboard.writeText(csv);

      logger.info('resources:csv', 'Copied to clipboard', { rowCount: items.length });
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      logger.error('resources:csv', 'Copy failed', { error: err.message });
    }
  }, [search, platform, dateFrom, dateTo]);

  const handleEnrichAll = async () => {
    logger.info('resources:enrichAll', 'Enrich all triggered', { search, platform, dateFrom, dateTo });
    setEnrichingAll(true);
    try {
      const params = new URLSearchParams({ page: 1, page_size: 5000 });
      if (search)   params.append('search',    search);
      if (platform) params.append('platform',  platform);
      if (dateFrom) params.append('date_from', dateFrom);
      if (dateTo)   params.append('date_to',   dateTo);

      const res = await fetch(`/api/resources?${params.toString()}`);
      if (!res.ok) throw new Error('Failed to fetch resources for enrich all');
      const { items } = await res.json();

      const toEnrich = items.filter(r => 
        r.enrichment_status !== 'done' && 
        r.enrichment_status !== 'pending' &&
        !enrichingIds.has(r.id)
      );

      if (toEnrich.length === 0) {
        logger.info('resources:enrichAll', 'No resources to enrich');
        setEnrichingAll(false);
        return;
      }

      const currentPageIds = new Set(resources.map(r => r.id));

      for (let i = 0; i < toEnrich.length; i += 5) {
        const chunk = toEnrich.slice(i, i + 5);
        await Promise.all(chunk.map(async (r) => {
          if (currentPageIds.has(r.id)) {
            handleEnrich(null, r.id);
          } else {
            await fetch(`/api/resources/${r.id}/enrich`, { method: 'POST' }).catch(err => {
              logger.warn('resources:enrichAll', `Failed to enrich ${r.id}`, { error: err.message });
            });
          }
        }));
      }
      logger.info('resources:enrichAll', 'Enrich all completed', { count: toEnrich.length });
    } catch (err) {
      logger.error('resources:enrichAll', 'Enrich all failed', { error: err.message });
    } finally {
      setEnrichingAll(false);
    }
  };

  const fetchResources = async () => {
    logger.debug('resources:fetch', 'Fetch resources started', { page, search, platform, dateFrom, dateTo });
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page,
        page_size: pageSize,
      });
      if (search) params.append('search', search);
      if (platform) params.append('platform', platform);
      if (dateFrom) params.append('date_from', dateFrom);
      if (dateTo) params.append('date_to', dateTo);

      const response = await fetch(`/api/resources?${params.toString()}`);
      if (!response.ok) throw new Error('Failed to fetch resources');
      
      const data = await response.json();
      setResources(data.items);
      setTotal(data.total);
      logger.info('resources:fetch', 'Data loaded', { count: data.items.length, total: data.total });
    } catch (err) {
      logger.warn('resources:fetch', 'API error', { detail: err.message });
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchResources();
  }, [page, search, platform, dateFrom, dateTo]);

  // Clean up polling timers on unmount
  useEffect(() => {
    return () => {
      Object.values(pollingTimers.current).forEach(clearInterval);
    };
  }, []);

  const toggleExpand = (id) => {
    setExpandedId(expandedId === id ? null : id);
  };

  /**
   * Trigger the LLM enrichment workflow for a single resource.
   */
  const handleEnrich = useCallback(async (e, resourceId) => {
    if (e) e.stopPropagation(); // don't toggle row expand

    logger.info('resources:enrich', 'Enrich triggered', { resourceId });

    // Optimistic UI: mark pending immediately
    setEnrichingIds(prev => new Set([...prev, resourceId]));
    setResources(prev =>
      prev.map(r => r.id === resourceId ? { ...r, enrichment_status: 'pending' } : r)
    );

    try {
      const res = await fetch(`/api/resources/${resourceId}/enrich`, { method: 'POST' });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }

      // Poll every 2 seconds until enrichment completes
      const timerId = setInterval(async () => {
        try {
          const poll = await fetch(`/api/resources/${resourceId}`);
          if (!poll.ok) return;
          const updated = await poll.json();
          logger.debug('resources:poll', 'Poll tick', { resourceId, enrichmentStatus: updated.enrichment_status });

          if (updated.enrichment_status !== 'pending') {
            // Done or failed — update row and stop polling
            logger.info('resources:enrich', 'Enrich done', { resourceId, status: updated.enrichment_status });
            clearInterval(pollingTimers.current[resourceId]);
            delete pollingTimers.current[resourceId];
            setEnrichingIds(prev => {
              const next = new Set(prev);
              next.delete(resourceId);
              return next;
            });
            setResources(prev =>
              prev.map(r => r.id === resourceId ? { ...r, ...updated } : r)
            );
            // Auto-expand so the user immediately sees the enriched content
            if (updated.enrichment_status === 'done') {
              setExpandedId(resourceId);
            }
          }
        } catch (pollErr) {
          logger.warn('resources:poll', 'Polling error', { error: pollErr.message });
        }
      }, 2000);

      pollingTimers.current[resourceId] = timerId;
    } catch (err) {
      logger.error('resources:enrich', 'Enrich failed', { error: err.message });
      setEnrichingIds(prev => {
        const next = new Set(prev);
        next.delete(resourceId);
        return next;
      });
      setResources(prev =>
        prev.map(r => r.id === resourceId ? { ...r, enrichment_status: 'failed' } : r)
      );
    }
  }, []);

  const totalPages = Math.ceil(total / pageSize);

  const getEnrichButtonState = (r) => {
    if (enrichingIds.has(r.id) || r.enrichment_status === 'pending') {
      return 'loading';
    }
    if (r.enrichment_status === 'done') return 're-enrich';
    if (r.enrichment_status === 'failed') return 'retry';
    return 'enrich';
  };

  return (
    <div className="resources-container fade-in">
      
      {/* Toolbar / Filters */}
      <div className="toolbar glass-panel">
        <div className="search-box">
          <Search size={18} className="search-icon" />
          <input 
            type="text" 
            placeholder="Search URLs or context..." 
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          />
        </div>
        
        <div className="filters">
          <div className="filter-group">
            <Filter size={16} />
            <select value={platform} onChange={(e) => { setPlatform(e.target.value); setPage(1); }}>
              <option value="">All Platforms</option>
              <option value="Instagram">Instagram</option>
              <option value="YouTube">YouTube</option>
              <option value="X/Twitter">X/Twitter</option>
              <option value="Google Maps">Google Maps</option>
              <option value="Spotify">Spotify</option>
            </select>
          </div>

          <div className="filter-group date-filter-group">
            <CalendarRange size={16} />
            <input
              type="date"
              className="date-input"
              title="From date"
              value={dateFrom}
              onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
            />
            <span className="date-separator">→</span>
            <input
              type="date"
              className="date-input"
              title="To date"
              value={dateTo}
              onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
            />
            {(dateFrom || dateTo) && (
              <button
                className="date-clear-btn"
                title="Clear date range"
                onClick={() => { setDateFrom(''); setDateTo(''); setPage(1); }}
              >
                <X size={13} />
              </button>
            )}
          </div>
        </div>

        <div className="toolbar-actions" style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            className="enrich-all-btn"
            onClick={handleEnrichAll}
            disabled={enrichingAll}
            title="Enrich all filtered results"
          >
            {enrichingAll ? <><Loader size={15} className="spin" /> Enriching...</> : <><Sparkles size={15} /> Enrich All</>}
          </button>
          
          <button
            className={`copy-csv-btn ${copied ? 'copy-csv-btn--copied' : ''}`}
            onClick={handleCopyCSV}
            title="Copy all filtered results as CSV"
          >
            {copied ? <><Check size={15} /> Copied!</> : <><Copy size={15} /> Copy CSV</>}
          </button>
        </div>
      </div>

      {/* Data Table */}
      <div className="table-container glass-panel">
        {loading && resources.length === 0 ? (
          <div className="loading-state">Loading resources...</div>
        ) : error ? (
          <div className="error-state">Error: {error}</div>
        ) : (
          <table className="resources-table">
            <thead>
              <tr>
                <th width="40px"></th>
                <th>Platform</th>
                <th>Sender</th>
                <th>URL</th>
                <th>Date</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {resources.length === 0 ? (
                <tr>
                  <td colSpan="6" className="empty-state">No resources found</td>
                </tr>
              ) : (
                resources.map(r => {
                  const enrichState = getEnrichButtonState(r);
                  return (
                    <React.Fragment key={r.id}>
                      <tr className={`resource-row ${expandedId === r.id ? 'expanded' : ''}`} onClick={() => toggleExpand(r.id)}>
                        <td className="expand-cell">
                          {expandedId === r.id ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                        </td>
                        <td>
                          <span className="platform-badge">{r.platform || 'Unknown'}</span>
                          {r.enrichment_status === 'done' && (
                            <span className="enriched-dot" title="AI enriched" />
                          )}
                        </td>
                        <td className="sender-cell">{r.sender || 'Unknown'}</td>
                        <td className="url-cell">
                          <a href={r.canonical_url || r.original_url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}>
                            {r.title || r.canonical_url || r.original_url} <ExternalLink size={14} className="ext-link-icon"/>
                          </a>
                          {/* Inline enrichment preview — visible without expanding */}
                          {r.enrichment_status === 'done' && r.notes && (
                            <p className="row-notes">{r.notes}</p>
                          )}
                          {r.enrichment_status === 'done' && r.tags && (
                            <div className="row-tags">
                              {r.tags.split(',').slice(0, 4).map(tag => (
                                <span key={tag.trim()} className="tag-chip tag-chip--sm">{tag.trim()}</span>
                              ))}
                            </div>
                          )}
                        </td>
                        <td className="date-cell">
                          {r.message_timestamp
                            ? new Date(r.message_timestamp.replace(' ', 'T')).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
                            : '—'}
                        </td>
                        <td className="actions-cell">
                          <button
                            className={`enrich-btn enrich-btn--${enrichState}`}
                            onClick={(e) => handleEnrich(e, r.id)}
                            disabled={enrichState === 'loading'}
                            title={
                              enrichState === 'loading' ? 'Enriching…' :
                              enrichState === 're-enrich' ? 'Re-enrich with latest data' :
                              enrichState === 'retry' ? 'Retry enrichment (previous attempt failed)' :
                              'Fetch metadata with AI'
                            }
                          >
                            {enrichState === 'loading' ? (
                              <><Loader size={13} className="spin" /> Enriching…</>
                            ) : enrichState === 're-enrich' ? (
                              <><RefreshCw size={13} /> Re-enrich</>
                            ) : enrichState === 'retry' ? (
                              <><RefreshCw size={13} /> Retry</>
                            ) : (
                              <><Sparkles size={13} /> Enrich</>
                            )}
                          </button>
                        </td>
                      </tr>
                      
                      {/* Expanded Context Row */}
                      {expandedId === r.id && (
                        <tr className="context-row">
                          <td colSpan="6">
                            <div className="context-panel">
                              {/* Enriched metadata section */}
                              {r.enrichment_status === 'done' && (r.notes || r.tags) && (
                                <div className="enriched-section">
                                  <h4>✨ AI Enrichment</h4>
                                  {r.notes && <p className="enriched-notes">{r.notes}</p>}
                                  {r.tags && (
                                    <div className="enriched-tags">
                                      {r.tags.split(',').map(tag => (
                                        <span key={tag.trim()} className="tag-chip">{tag.trim()}</span>
                                      ))}
                                    </div>
                                  )}
                                  {r.enriched_at && (
                                    <p className="enriched-at">Enriched {new Date(r.enriched_at + 'Z').toLocaleString()}</p>
                                  )}
                                </div>
                              )}

                              {r.enrichment_status === 'failed' && (
                                <div className="enrichment-failed">
                                  <p>⚠️ Enrichment failed</p>
                                  {r.enrichment_error && (
                                    <p className="enrichment-error-detail">{r.enrichment_error.length > 200 ? r.enrichment_error.slice(0, 200) + '…' : r.enrichment_error}</p>
                                  )}
                                </div>
                              )}

                              <h4>Message Context</h4>
                              <pre className="context-text">{r.context || 'No context available.'}</pre>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {!loading && totalPages > 1 && (
        <div className="pagination">
          <button 
            disabled={page === 1} 
            onClick={() => setPage(p => Math.max(1, p - 1))}
            className="glass-panel"
          >
            Previous
          </button>
          <span className="page-info">Page {page} of {totalPages}</span>
          <button 
            disabled={page === totalPages} 
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            className="glass-panel"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
