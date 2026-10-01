import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { MessageSquare, ArrowLeft, Calendar, BarChart2, Users, Link2, Sparkles, History } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, LineChart, Line } from 'recharts';
import logger from '../lib/logger';
import './Chats.css';

export default function ChatInsights() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const [summary, setSummary] = useState(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [summaryError, setSummaryError] = useState(null);

  const [pastSummaries, setPastSummaries] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  const fetchInsights = async () => {
    logger.debug('chat-insights:fetch', 'Fetching insights', { id, dateFrom, dateTo });
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (dateFrom) params.append('date_from', dateFrom);
      if (dateTo) params.append('date_to', dateTo);
      
      const url = `/api/chats/${id}/insights?${params.toString()}`;
      const response = await fetch(url);
      if (!response.ok) throw new Error('Failed to fetch chat insights');
      
      const json = await response.json();
      setData(json);
      logger.info('chat-insights:fetch', 'Insights loaded', { id });
    } catch (err) {
      logger.warn('chat-insights:fetch', 'API error', { detail: err.message });
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchPastSummaries = async () => {
    try {
      const response = await fetch(`/api/chats/${id}/summaries`);
      if (response.ok) {
        const json = await response.json();
        setPastSummaries(json);
      }
    } catch (err) {
      logger.warn('chat-insights:history', 'Failed to fetch past summaries', { detail: err.message });
    }
  };

  useEffect(() => {
    fetchInsights();
  }, [id, dateFrom, dateTo]);

  useEffect(() => {
    fetchPastSummaries();
  }, [id]);

  const handleDateReset = () => {
    setDateFrom('');
    setDateTo('');
  };

  const generateSummary = async () => {
    logger.debug('chat-insights:summary', 'Generating summary', { id, dateFrom, dateTo });
    setLoadingSummary(true);
    setSummaryError(null);
    setSummary(null);
    try {
      const params = new URLSearchParams();
      if (dateFrom) params.append('date_from', dateFrom);
      if (dateTo) params.append('date_to', dateTo);
      
      const url = `/api/chats/${id}/summary?${params.toString()}`;
      const response = await fetch(url, { method: 'POST' });
      const json = await response.json();
      
      if (!response.ok) throw new Error(json.detail || 'Failed to generate summary');
      
      setSummary(json.summary);
      fetchPastSummaries();
      logger.info('chat-insights:summary', 'Summary generated');
    } catch (err) {
      logger.warn('chat-insights:summary', 'API error', { detail: err.message });
      setSummaryError(err.message);
    } finally {
      setLoadingSummary(false);
    }
  };

  const handleGenerateSummaryClick = () => {
    if (data.total_messages > 200) {
      const confirmed = window.confirm(
        `This segment contains ${data.total_messages} messages.\n\nGenerating a summary for this many messages may take a while and use significant AI resources. Do you want to proceed?`
      );
      if (!confirmed) return;
    }
    generateSummary();
  };

  return (
    <div className="chats-container fade-in">
      <div className="toolbar glass-panel" style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
        <Link to="/chats" className="btn btn-secondary" style={{ textDecoration: 'none' }}>
          <ArrowLeft size={16} />
          Back
        </Link>
        <div className="toolbar-title" style={{ flex: 1, marginLeft: '8px' }}>
          <BarChart2 size={20} className="toolbar-icon" />
          <h2>{data ? data.chat_name : 'Loading...'} Insights</h2>
        </div>
        
        <div className="filters-row" style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <div className="filter-group">
            <Calendar size={16} />
            <input 
              type="date" 
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="filter-input"
            />
            <span style={{color: 'var(--text-secondary)'}}>to</span>
            <input 
              type="date" 
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="filter-input"
            />
            {(dateFrom || dateTo) && (
               <button onClick={handleDateReset} className="btn btn-secondary" style={{ marginLeft: '8px' }}>
                 Reset
               </button>
            )}
          </div>
        </div>
      </div>

      {loading && !data ? (
        <div className="loading-state glass-panel">Loading insights...</div>
      ) : error ? (
        <div className="error-state glass-panel">Error: {error}</div>
      ) : data ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          <div className="glass-panel" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
                <Sparkles size={18} color="var(--accent-purple)" />
                AI Chat Summary
              </h3>
              <div style={{ display: 'flex', gap: '12px' }}>
                <button 
                  className="btn btn-secondary" 
                  onClick={() => setShowHistory(!showHistory)}
                  disabled={pastSummaries.length === 0}
                  title="View past summaries"
                >
                  <History size={16} />
                  {pastSummaries.length > 0 ? `History (${pastSummaries.length})` : 'History'}
                </button>
                <button 
                  className="btn btn-primary" 
                  onClick={handleGenerateSummaryClick} 
                  disabled={loadingSummary || data.total_messages === 0}
                  style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
                >
                  {loadingSummary ? 'Summarizing...' : 'Generate Summary'}
                </button>
              </div>
            </div>
            
            {showHistory && pastSummaries.length > 0 && (
              <div style={{ marginBottom: '20px', padding: '16px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                <h4 style={{ margin: '0 0 12px 0', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Past Summaries</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {pastSummaries.map((s) => (
                    <div 
                      key={s.id} 
                      style={{ padding: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '6px', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                      onClick={() => {
                        setSummary(s.summary);
                        setDateFrom(s.date_from || '');
                        setDateTo(s.date_to || '');
                        setShowHistory(false);
                      }}
                    >
                      <div>
                        <div style={{ fontSize: '0.875rem', color: 'var(--text-primary)' }}>
                          {s.date_from || s.date_to ? (
                            <>Dates: {s.date_from || 'Any'} to {s.date_to || 'Any'}</>
                          ) : (
                            'Full Chat Summary'
                          )}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                          Generated on {new Date(s.created_at).toLocaleString()}
                        </div>
                      </div>
                      <span className="btn btn-secondary" style={{ fontSize: '0.75rem', padding: '4px 8px' }}>Load</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {summaryError && <div className="error-state" style={{ marginBottom: '16px' }}>Error: {summaryError}</div>}
            
            {summary ? (
              <div className="summary-content" style={{ whiteSpace: 'pre-wrap', lineHeight: '1.6', color: 'var(--text-primary)' }}>
                {summary}
              </div>
            ) : !loadingSummary && (
              <div className="empty-state" style={{ margin: 0, padding: '24px 0' }}>
                {data.total_messages > 0 
                  ? 'Click "Generate Summary" to get an AI summary for this date range.' 
                  : 'No messages to summarize in this date range.'}
              </div>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
          
            <div className="glass-panel" style={{ padding: '24px' }}>
            <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
              <MessageSquare size={18} />
              Total Messages: {data.total_messages.toLocaleString()}
            </h3>
            <div style={{ height: 300 }}>
              {data.daily_activity.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.daily_activity}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis 
                      dataKey="date" 
                      stroke="var(--text-secondary)" 
                      tickFormatter={(val) => {
                        // If it's an hourly format "YYYY-MM-DD HH:00", show just day and hour like "01-01 14:00"
                        if (val.length > 10) return val.substring(5, 16);
                        return val;
                      }}
                      tick={{ fontSize: 12 }}
                    />
                    <YAxis stroke="var(--text-secondary)" tick={{ fontSize: 12 }} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: '8px' }}
                      labelStyle={{ color: 'var(--text-primary)' }}
                    />
                    <Line type="monotone" dataKey="count" stroke="var(--accent-purple)" strokeWidth={2} dot={{ fill: 'var(--accent-purple)', r: 3 }} activeDot={{ r: 5 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="empty-state">No activity in this date range.</div>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div className="glass-panel" style={{ padding: '24px', flex: 1 }}>
              <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
                <Users size={18} />
                Top Participants
              </h3>
              {data.participants.length > 0 ? (
                <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {data.participants.slice(0, 5).map((p, i) => (
                    <li key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span>{p.sender}</span>
                      <span className="badge badge-primary">{p.count.toLocaleString()}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="empty-state">No participants found.</div>
              )}
            </div>

            <div className="glass-panel" style={{ padding: '24px', flex: 1 }}>
              <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
                <Link2 size={18} />
                Top Platforms Shared
              </h3>
              {data.top_platforms.length > 0 ? (
                <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {data.top_platforms.slice(0, 5).map((p, i) => (
                    <li key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span>{p.platform}</span>
                      <span className="badge badge-secondary">{p.count.toLocaleString()}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="empty-state">No resources shared.</div>
              )}
            </div>
          </div>
          </div>
          
        </div>
      ) : null}
    </div>
  );
}
