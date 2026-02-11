import React, { useState } from 'react';
import axios from 'axios';
import '../styles/Login.css';

function Login({ onLoginSuccess }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [mfaRequired, setMfaRequired] = useState(false);
  const [challengeId, setChallengeId] = useState('');
  const [mfaPolling, setMfaPolling] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await axios.post('/api/auth/login', {
        username,
        password
      });

      if (response.data.success) {
        // Login successful - store token and call success callback
        localStorage.setItem('auth_token', response.data.token);
        localStorage.setItem('robinhood_authenticated', 'true');
        onLoginSuccess(response.data.token);
      } else if (response.data.requires_mfa) {
        // MFA required - start polling
        setMfaRequired(true);
        setChallengeId(response.data.challenge_id);
        startMfaPolling(response.data.challenge_id);
      }
    } catch (err) {
      console.error('Login error:', err);
      setError(
        err.response?.data?.detail ||
        err.message ||
        'Login failed. Please check your credentials.'
      );
      setLoading(false);
    }
  };

  const startMfaPolling = (challengeId) => {
    setMfaPolling(true);

    // Poll every 3 seconds
    const pollInterval = setInterval(async () => {
      try {
        const response = await axios.post('/api/auth/mfa/check', {
          challenge_id: challengeId
        });

        if (response.data.success) {
          // MFA approved!
          clearInterval(pollInterval);
          setMfaPolling(false);
          localStorage.setItem('auth_token', response.data.token);
          localStorage.setItem('robinhood_authenticated', 'true');
          onLoginSuccess(response.data.token);
        } else if (response.data.pending) {
          // Still waiting...
          console.log('Waiting for MFA approval...');
        }
      } catch (err) {
        console.error('MFA check error:', err);
        clearInterval(pollInterval);
        setMfaPolling(false);
        setMfaRequired(false);
        setError(
          err.response?.data?.detail ||
          'MFA verification failed. Please try logging in again.'
        );
        setLoading(false);
      }
    }, 3000); // Poll every 3 seconds

    // Timeout after 5 minutes
    setTimeout(() => {
      clearInterval(pollInterval);
      if (mfaPolling) {
        setMfaPolling(false);
        setMfaRequired(false);
        setError('MFA timeout. Please try logging in again.');
        setLoading(false);
      }
    }, 5 * 60 * 1000);
  };

  const handleCancel = () => {
    setMfaRequired(false);
    setMfaPolling(false);
    setLoading(false);
    setError('');
  };

  const handleSkipLogin = () => {
    // Set a special token indicating user is in limited mode (no Robinhood auth)
    localStorage.setItem('auth_token', 'limited_mode');
    localStorage.setItem('robinhood_authenticated', 'false');
    onLoginSuccess('limited_mode');
  };

  return (
    <div className="login-container">
      <div className="login-box">
        <div className="login-header">
          <h1>🤖 AI Trading Bot</h1>
          <p>Login with your Robinhood credentials</p>
        </div>

        {!mfaRequired ? (
          <form onSubmit={handleLogin} className="login-form">
            <div className="form-group">
              <label htmlFor="username">Username</label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter Robinhood username"
                required
                disabled={loading}
                autoComplete="username"
              />
            </div>

            <div className="form-group">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter Robinhood password"
                required
                disabled={loading}
                autoComplete="current-password"
              />
            </div>

            {error && (
              <div className="error-message">
                <span className="error-icon">⚠️</span>
                {error}
              </div>
            )}

            <button
              type="submit"
              className="login-button"
              disabled={loading || !username || !password}
            >
              {loading ? 'Logging in...' : 'Login to Robinhood'}
            </button>

            <button
              type="button"
              className="skip-button"
              onClick={handleSkipLogin}
              disabled={loading}
            >
              Continue Without Trading
            </button>

            <div className="login-footer">
              <p>
                <span className="info-icon">ℹ️</span>
                Your credentials are never stored. Sessions expire after 24 hours.
              </p>
              <p className="skip-info">
                Skip login to use chat, screener, and settings without trading capabilities.
              </p>
            </div>
          </form>
        ) : (
          <div className="mfa-container">
            <div className="mfa-spinner">
              <div className="spinner"></div>
            </div>

            <h2>MFA Required</h2>

            <p className="mfa-message">
              Please approve the login request in your <strong>Robinhood app</strong>.
            </p>

            <div className="mfa-instructions">
              <p>1. Open the Robinhood app on your phone</p>
              <p>2. Approve the login notification</p>
              <p>3. Wait for automatic redirect</p>
            </div>

            {mfaPolling && (
              <div className="mfa-status">
                <span className="pulse-dot"></span>
                Waiting for approval...
              </div>
            )}

            {error && (
              <div className="error-message">
                <span className="error-icon">⚠️</span>
                {error}
              </div>
            )}

            <button
              onClick={handleCancel}
              className="cancel-button"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default Login;
