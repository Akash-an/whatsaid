import React, { useState, useEffect } from 'react';
import { MessageSquare, Calendar } from 'lucide-react';
import './Chats.css';

export default function Chats() {
  const [chats, setChats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchChats = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/chats');
      if (!response.ok) throw new Error('Failed to fetch chats');
      
      const data = await response.json();
      setChats(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchChats();
  }, []);

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    
    // WhatsApp exports dates in local formats (e.g., "31/08/26, 7:40 pm").
    // Parsing this directly with new Date() causes "Invalid Date" for days > 12.
    // It's safer to display the raw string provided by the export.
    return dateString;
  };

  return (
    <div className="chats-container fade-in">
      <div className="toolbar glass-panel">
        <div className="toolbar-title">
          <MessageSquare size={20} className="toolbar-icon" />
          <h2>Imported Chats</h2>
        </div>
        <div className="toolbar-stats">
          Total Chats: {chats.length}
        </div>
      </div>

      <div className="table-container glass-panel">
        {loading ? (
          <div className="loading-state">Loading chats...</div>
        ) : error ? (
          <div className="error-state">Error: {error}</div>
        ) : (
          <table className="chats-table">
            <thead>
              <tr>
                <th>Chat Name</th>
                <th>Messages</th>
                <th>Imports</th>
                <th>First Message</th>
                <th>Last Message</th>
              </tr>
            </thead>
            <tbody>
              {chats.length === 0 ? (
                <tr>
                  <td colSpan="5" className="empty-state">No chats found. Import some data to get started.</td>
                </tr>
              ) : (
                chats.map(chat => (
                  <tr key={chat.id} className="chat-row">
                    <td className="chat-name-cell">
                      <MessageSquare size={16} className="chat-icon" />
                      {chat.name}
                    </td>
                    <td className="metric-cell">
                      <span className="badge badge-primary">{chat.message_count.toLocaleString()}</span>
                    </td>
                    <td className="metric-cell">
                      <span className="badge badge-secondary">{chat.import_count.toLocaleString()}</span>
                    </td>
                    <td className="date-cell">
                      <Calendar size={14} className="date-icon" />
                      {formatDate(chat.first_message_at)}
                    </td>
                    <td className="date-cell">
                      <Calendar size={14} className="date-icon" />
                      {formatDate(chat.last_message_at)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
