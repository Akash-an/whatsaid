import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom';
import { LayoutDashboard, Link2, MessageSquare, MessageCircle, Sparkles, Terminal } from 'lucide-react';

import Dashboard from './pages/Dashboard';
import Resources from './pages/Resources';
import Chats from './pages/Chats';
import Messages from './pages/Messages';
import Ask from './pages/Ask';
import Logs from './pages/Logs';


function App() {
  return (
    <Router>
      <div className="app-container">
        {/* Sidebar */}
        <aside className="sidebar">
          <div className="sidebar-logo">
            <MessageCircle size={28} color="var(--accent-purple)" />
            Whatsaid
          </div>
          
          <nav>
            <ul className="nav-menu">
              <li>
                <NavLink to="/" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                  <LayoutDashboard size={20} />
                  Dashboard
                </NavLink>
              </li>
              <li>
                <NavLink to="/resources" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                  <Link2 size={20} />
                  Resources
                </NavLink>
              </li>
              <li>
                <NavLink to="/chats" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                  <MessageSquare size={20} />
                  Chats
                </NavLink>
              </li>
              <li>
                <NavLink to="/messages" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                  <MessageCircle size={20} />
                  Messages
                </NavLink>
              </li>
              <li>
                <NavLink to="/ask" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                  <Sparkles size={20} />
                  Ask
                </NavLink>
              </li>
              <li>
                <NavLink to="/logs" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                  <Terminal size={20} />
                  Logs
                </NavLink>
              </li>
            </ul>
          </nav>
        </aside>

        {/* Main Content Area */}
        <main className="main-content">
          <header className="header">
            <h1>Chat Insights</h1>
          </header>
          
          <div className="page-container">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/resources" element={<Resources />} />
              <Route path="/chats" element={<Chats />} />
              <Route path="/messages" element={<Messages />} />
              <Route path="/ask" element={<Ask />} />
              <Route path="/logs" element={<Logs />} />
            </Routes>
          </div>
        </main>
      </div>
    </Router>
  );
}

export default App;
