import React, { useState, useEffect, useMemo } from 'react';
import { Terminal, RefreshCw, Filter, Search, ChevronDown, ChevronRight, AlertCircle, Info, Bug, Activity } from 'lucide-react';
import './Logs.css';
import logger from '../lib/logger';

const LEVEL_COLORS = {
  DEBUG: 'var(--text-secondary)',
  INFO: 'var(--accent-cyan)',
  WARNING: 'var(--accent-yellow)',
  WARN: 'var(--accent-yellow)',
  ERROR: 'var(--accent-red)',
  CRITICAL: 'var(--accent-red)',
};

const LEVEL_ICONS = {
  DEBUG: <Bug size={14} />,
  INFO: <Info size={14} />,
  WARNING: <AlertCircle size={14} />,
  WARN: <AlertCircle size={14} />,
  ERROR: <AlertCircle size={14} />,
  CRITICAL: <AlertCircle size={14} />,
};

function LogRow({ log }) {
  const [expanded, setExpanded] = useState(false);
  
  // Extract standard fields
  const { ts, level, logger: logName, namespace, msg, request_id, exc, ...extra } = log;
  const displayLevel = (level || '').toUpperCase();
  const displayName = logName || namespace || 'app';
  const color = LEVEL_COLORS[displayLevel] || 'var(--text-primary)';
  
  const hasExtra = Object.keys(extra).length > 0 || exc;

  return (
    <div className={`log-row ${expanded ? 'expanded' : ''}`}>
      <div className="log-summary" onClick={() => hasExtra && setExpanded(!expanded)}>
        <div className="log-expand-icon">
          {hasExtra ? (expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : <span style={{ width: 14 }} />}
        </div>
        <div className="log-time">{new Date(ts).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute:'2-digit', second:'2-digit', fractionalSecondDigits: 3 })}</div>
        <div className="log-level" style={{ color }}>
          {LEVEL_ICONS[displayLevel]}
          <span>{displayLevel.padEnd(5)}</span>
        </div>
        <div className="log-name">{displayName}</div>
        <div className="log-msg">
          {request_id && <span className="log-req-id">[{request_id}]</span>}
          {msg}
        </div>
      </div>
      
      {expanded && hasExtra && (
        <div className="log-details">
          {exc && (
            <div className="log-exc">
              <pre>{exc}</pre>
            </div>
          )}
          {Object.keys(extra).length > 0 && (
            <div className="log-json">
              <pre>{JSON.stringify(extra, null, 2)}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Logs() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [file, setFile] = useState('whatsaid.log');
  const [search, setSearch] = useState('');
  const [levelFilter, setLevelFilter] = useState('');

  const fetchLogs = async () => {
    logger.debug('logs:fetch', 'Fetching logs', { file });
    setLoading(true);
    try {
      const response = await fetch(`/api/logs?file=${file}`);
      if (!response.ok) throw new Error('Failed to fetch logs');
      const data = await response.json();
      setLogs(data);
      setError(null);
    } catch (err) {
      logger.error('logs:fetch', 'Failed to fetch logs', { error: err.message });
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
    // Optional auto-refresh interval could go here
    // const int = setInterval(fetchLogs, 5000);
    // return () => clearInterval(int);
  }, [file]);

  const filteredLogs = useMemo(() => {
    return logs.filter(log => {
      const matchSearch = search === '' || 
        JSON.stringify(log).toLowerCase().includes(search.toLowerCase());
      
      const displayLevel = (log.level || '').toUpperCase();
      const matchLevel = levelFilter === '' || 
        (levelFilter === 'WARN_ERROR' ? ['WARNING', 'WARN', 'ERROR', 'CRITICAL'].includes(displayLevel) : displayLevel === levelFilter);
        
      return matchSearch && matchLevel;
    });
  }, [logs, search, levelFilter]);

  return (
    <div className="logs-container fade-in">
      <div className="toolbar glass-panel">
        <div className="toolbar-left">
          <Terminal size={20} className="toolbar-icon" style={{ color: 'var(--accent-purple)' }} />
          <h2>System Logs</h2>
          
          <div className="filter-group" style={{ marginLeft: '1rem' }}>
            <select value={file} onChange={e => setFile(e.target.value)} className="log-file-select">
              <option value="whatsaid.log">Backend Logs (whatsaid.log)</option>
              <option value="ui.log">Frontend Logs (ui.log)</option>
              <option value="llm.log">LLM I/O (llm.log)</option>
            </select>
          </div>
        </div>

        <div className="toolbar-actions">
          <div className="search-box">
            <Search size={16} className="search-icon" />
            <input 
              type="text" 
              placeholder="Search in logs..." 
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>

          <div className="filter-group">
            <Filter size={16} />
            <select value={levelFilter} onChange={e => setLevelFilter(e.target.value)}>
              <option value="">All Levels</option>
              <option value="INFO">Info</option>
              <option value="DEBUG">Debug</option>
              <option value="WARN_ERROR">Warn & Error</option>
            </select>
          </div>
          
          <button className="refresh-btn" onClick={fetchLogs} disabled={loading} title="Refresh logs">
            <RefreshCw size={16} className={loading ? 'spin' : ''} />
          </button>
        </div>
      </div>

      <div className="log-viewer glass-panel">
        {error ? (
          <div className="error-state">
            <AlertCircle size={24} />
            <p>Error loading logs: {error}</p>
          </div>
        ) : (
          <div className="log-list">
            {filteredLogs.length === 0 ? (
              <div className="empty-state">No logs found matching your criteria.</div>
            ) : (
              filteredLogs.map((log, i) => (
                <LogRow key={`${log.ts}-${i}`} log={log} />
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
