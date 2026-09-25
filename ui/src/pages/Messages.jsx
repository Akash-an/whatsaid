import React, { useState, useEffect } from 'react';
import { Search, MessageCircle, Calendar, User } from 'lucide-react';
import './Messages.css';

export default function Messages() {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Pagination & Filtering state
  const [page, setPage] = useState(1);
  const [pageSize] = useState(100);
  const [total, setTotal] = useState(0);
  
  const [search, setSearch] = useState('');

  const fetchMessages = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page,
        page_size: pageSize,
      });
      if (search) params.append('search', search);

      const response = await fetch(`/api/messages?${params.toString()}`);
      if (!response.ok) throw new Error('Failed to fetch messages');
      
      const data = await response.json();
      setMessages(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMessages();
  }, [page, search]);

  const totalPages = Math.ceil(total / pageSize);

  const formatTimestamp = (ts) => {
    if (!ts) return 'Unknown';
    // WhatsApp exports dates in local formats (e.g., "31/08/26, 7:40 pm").
    // Avoid parsing with new Date() to prevent "Invalid Date" errors.
    return ts;
  };

  return (
    <div className="messages-container fade-in">
      {/* Toolbar / Filters */}
      <div className="toolbar glass-panel">
        <div className="search-box">
          <Search size={18} className="search-icon" />
          <input 
            type="text" 
            placeholder="Search message text..." 
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          />
        </div>
        <div className="toolbar-stats">
          {total.toLocaleString()} Messages
        </div>
      </div>

      {/* Data Table */}
      <div className="table-container glass-panel">
        {loading && messages.length === 0 ? (
          <div className="loading-state">Loading messages...</div>
        ) : error ? (
          <div className="error-state">Error: {error}</div>
        ) : (
          <table className="messages-table">
            <thead>
              <tr>
                <th width="180px">Timestamp</th>
                <th width="150px">Sender</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {messages.length === 0 ? (
                <tr>
                  <td colSpan="3" className="empty-state">No messages found</td>
                </tr>
              ) : (
                messages.map(m => (
                  <tr key={m.id} className="message-row">
                    <td className="timestamp-cell">
                      <Calendar size={14} className="cell-icon" />
                      {formatTimestamp(m.timestamp)}
                    </td>
                    <td className="sender-cell">
                      <User size={14} className="cell-icon" />
                      {m.sender || 'Unknown'}
                    </td>
                    <td className="text-cell">
                      {m.text || <span className="empty-text">No text content</span>}
                    </td>
                  </tr>
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
