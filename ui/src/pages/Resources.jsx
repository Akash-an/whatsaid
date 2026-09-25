import React, { useState, useEffect } from 'react';
import { Search, ChevronDown, ChevronUp, ExternalLink, Filter } from 'lucide-react';
import './Resources.css';

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
  const [status, setStatus] = useState('');

  // Expanded row state
  const [expandedId, setExpandedId] = useState(null);

  const fetchResources = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page,
        page_size: pageSize,
      });
      if (search) params.append('search', search);
      if (platform) params.append('platform', platform);
      if (status) params.append('status', status);

      const response = await fetch(`/api/resources?${params.toString()}`);
      if (!response.ok) throw new Error('Failed to fetch resources');
      
      const data = await response.json();
      setResources(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchResources();
  }, [page, search, platform, status]);

  const toggleExpand = (id) => {
    setExpandedId(expandedId === id ? null : id);
  };

  const handleStatusChange = async (id, newStatus) => {
    try {
      const res = await fetch(`/api/resources/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      });
      if (res.ok) {
        // Update local state
        setResources(resources.map(r => r.id === id ? { ...r, status: newStatus } : r));
      }
    } catch (e) {
      console.error("Failed to update status", e);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

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
          
          <div className="filter-group">
            <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
              <option value="">All Statuses</option>
              <option value="To Review">To Review</option>
              <option value="Approved">Approved</option>
              <option value="Archived">Archived</option>
            </select>
          </div>
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
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {resources.length === 0 ? (
                <tr>
                  <td colSpan="6" className="empty-state">No resources found</td>
                </tr>
              ) : (
                resources.map(r => (
                  <React.Fragment key={r.id}>
                    <tr className={`resource-row ${expandedId === r.id ? 'expanded' : ''}`} onClick={() => toggleExpand(r.id)}>
                      <td className="expand-cell">
                        {expandedId === r.id ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                      </td>
                      <td>
                        <span className="platform-badge">{r.platform || 'Unknown'}</span>
                      </td>
                      <td className="sender-cell">{r.sender || 'Unknown'}</td>
                      <td className="url-cell">
                        <a href={r.canonical_url || r.original_url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}>
                          {r.title || r.canonical_url || r.original_url} <ExternalLink size={14} className="ext-link-icon"/>
                        </a>
                      </td>
                      <td>
                        <span className={`status-badge ${r.status ? r.status.toLowerCase().replace(' ', '-') : ''}`}>
                          {r.status || 'To Review'}
                        </span>
                      </td>
                      <td className="actions-cell" onClick={e => e.stopPropagation()}>
                        <select 
                          className="status-select"
                          value={r.status || 'To Review'} 
                          onChange={(e) => handleStatusChange(r.id, e.target.value)}
                        >
                          <option value="To Review">To Review</option>
                          <option value="Approved">Approved</option>
                          <option value="Archived">Archived</option>
                        </select>
                      </td>
                    </tr>
                    
                    {/* Expanded Context Row */}
                    {expandedId === r.id && (
                      <tr className="context-row">
                        <td colSpan="6">
                          <div className="context-panel">
                            <h4>Message Context</h4>
                            <pre className="context-text">{r.context || 'No context available.'}</pre>
                            
                            {r.notes && (
                              <div className="notes-section">
                                <h4>Notes</h4>
                                <p>{r.notes}</p>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))
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
