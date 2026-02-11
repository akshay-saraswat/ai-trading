import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './styles/App.css';
import ChatTab from './components/ChatTab';
import ViewTab from './components/ViewTab';
import InsightsTab from './components/InsightsTab';
import SettingsTab from './components/SettingsTab';
import MFAModal from './components/MFAModal';
import Login from './components/Login';

function App() {
  const [activeTab, setActiveTab] = useState('chat');
  const [loginStatus, setLoginStatus] = useState({ status: 'idle', message: '' });
  const [authenticated, setAuthenticated] = useState(false);
  const [robinhoodAuthenticated, setRobinhoodAuthenticated] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);

  // Theme management - default to system preference
  const [theme, setTheme] = useState(() => {
    // First check localStorage
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
      return savedTheme;
    }

    // If no saved theme, check system preference
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
      return 'light';
    }

    // Default to dark if no preference detected
    return 'dark';
  });

  useEffect(() => {
    // Apply theme to document
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  // Check authentication status on mount
  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem('auth_token');
      const rhAuth = localStorage.getItem('robinhood_authenticated') === 'true';

      if (!token) {
        setCheckingAuth(false);
        setAuthenticated(false);
        setRobinhoodAuthenticated(false);
        return;
      }

      // Check if user is in limited mode (skipped login)
      if (token === 'limited_mode') {
        setAuthenticated(true);
        setRobinhoodAuthenticated(false);
        setCheckingAuth(false);
        setLoginStatus({ status: 'success', message: 'Limited mode - No trading' });
        return;
      }

      try {
        // Configure axios to use token
        axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;

        const response = await axios.get('/api/auth/session');

        if (response.data.authenticated) {
          setAuthenticated(true);
          setRobinhoodAuthenticated(rhAuth);
          setLoginStatus({ status: 'success', message: rhAuth ? 'Logged in' : 'Limited mode' });
        } else {
          // Token invalid - clear it
          localStorage.removeItem('auth_token');
          localStorage.removeItem('robinhood_authenticated');
          delete axios.defaults.headers.common['Authorization'];
          setAuthenticated(false);
          setRobinhoodAuthenticated(false);
        }
      } catch (error) {
        console.error('Auth check error:', error);
        localStorage.removeItem('auth_token');
        localStorage.removeItem('robinhood_authenticated');
        delete axios.defaults.headers.common['Authorization'];
        setAuthenticated(false);
        setRobinhoodAuthenticated(false);
      } finally {
        setCheckingAuth(false);
      }
    };

    checkAuth();
  }, []);

  const toggleTheme = () => {
    setTheme(prevTheme => prevTheme === 'dark' ? 'light' : 'dark');
  };

  const handleLoginSuccess = (token) => {
    const rhAuth = localStorage.getItem('robinhood_authenticated') === 'true';

    // Configure axios to use the token (unless in limited mode)
    if (token !== 'limited_mode') {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    }

    setAuthenticated(true);
    setRobinhoodAuthenticated(rhAuth);
    setLoginStatus({
      status: 'success',
      message: rhAuth ? 'Logged in successfully' : 'Limited mode - No trading'
    });
  };

  const handleLogout = () => {
    const token = localStorage.getItem('auth_token');
    if (token && token !== 'limited_mode') {
      // Call logout endpoint for real sessions
      axios.post('/api/auth/logout').catch(console.error);
    }

    // Clear local state
    localStorage.removeItem('auth_token');
    localStorage.removeItem('robinhood_authenticated');
    delete axios.defaults.headers.common['Authorization'];
    setAuthenticated(false);
    setRobinhoodAuthenticated(false);
    setLoginStatus({ status: 'idle', message: '' });
  };

  const handleLoginRedirect = () => {
    // Clear limited mode and show login page
    handleLogout();
  };

  // Show loading while checking auth
  if (checkingAuth) {
    return (
      <div className="app">
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100vh',
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          color: 'white',
          fontSize: '18px'
        }}>
          Loading...
        </div>
      </div>
    );
  }

  // Show login screen if not authenticated
  if (!authenticated) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <div className="app">
      {/* MFA Modal */}
      <MFAModal
        status={loginStatus.status}
        message={loginStatus.message}
      />

      {/* Header */}
      <div className="app-header">
        <div className="header-content">
          <div className="header-text">
            <h1>⚡ Slick Trade</h1>
            <p className="app-subtitle">AI-Powered Options Trading Platform</p>
          </div>

          {/* Desktop Menu Buttons */}
          <div className="header-nav desktop-nav">
            <button
              className={`nav-menu-button ${activeTab === 'chat' ? 'active' : ''}`}
              onClick={() => setActiveTab('chat')}
            >
              💬 Chat
            </button>
            {robinhoodAuthenticated && (
              <button
                className={`nav-menu-button ${activeTab === 'view' ? 'active' : ''}`}
                onClick={() => setActiveTab('view')}
              >
                📊 Monitor
              </button>
            )}
            <button
              className={`nav-menu-button ${activeTab === 'insights' ? 'active' : ''}`}
              onClick={() => setActiveTab('insights')}
            >
              🔍 Screener
            </button>
            <button
              className={`nav-menu-button ${activeTab === 'settings' ? 'active' : ''}`}
              onClick={() => setActiveTab('settings')}
            >
              ⚙️ Settings
            </button>
          </div>

          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <button className="theme-toggle" onClick={toggleTheme} title="Toggle theme">
              {theme === 'dark' ? (
                <i className="fas fa-sun"></i>
              ) : (
                <i className="fas fa-moon"></i>
              )}
            </button>
            {robinhoodAuthenticated ? (
              <button
                className="logout-button"
                onClick={handleLogout}
                title="Logout"
                style={{
                  padding: '8px 16px',
                  background: 'rgba(239, 68, 68, 0.1)',
                  color: 'var(--error-color, #ef4444)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: '600',
                  transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(239, 68, 68, 0.2)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)';
                }}
              >
                🚪 Logout
              </button>
            ) : (
              <button
                className="login-button"
                onClick={handleLoginRedirect}
                title="Login to Robinhood"
                style={{
                  padding: '8px 16px',
                  background: 'rgba(34, 197, 94, 0.1)',
                  color: 'var(--success-color, #22c55e)',
                  border: '1px solid rgba(34, 197, 94, 0.3)',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: '600',
                  transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(34, 197, 94, 0.2)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(34, 197, 94, 0.1)';
                }}
              >
                🔑 Login to Trade
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Mobile Tab Navigation */}
      <div className="tab-navigation mobile-nav">
        <button
          className={`tab-button ${activeTab === 'chat' ? 'active' : ''}`}
          onClick={() => setActiveTab('chat')}
        >
          💬 Chat
        </button>
        {robinhoodAuthenticated && (
          <button
            className={`tab-button ${activeTab === 'view' ? 'active' : ''}`}
            onClick={() => setActiveTab('view')}
          >
            📊 Monitor
          </button>
        )}
        <button
          className={`tab-button ${activeTab === 'insights' ? 'active' : ''}`}
          onClick={() => setActiveTab('insights')}
        >
          🔍 Screener
        </button>
        <button
          className={`tab-button ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
        >
          ⚙️ Settings
        </button>
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'chat' && <ChatTab robinhoodAuthenticated={robinhoodAuthenticated} />}
        {activeTab === 'view' && robinhoodAuthenticated && <ViewTab robinhoodAuthenticated={robinhoodAuthenticated} />}
        {activeTab === 'insights' && <InsightsTab robinhoodAuthenticated={robinhoodAuthenticated} />}
        {activeTab === 'settings' && <SettingsTab />}
      </div>
    </div>
  );
}

export default App;
