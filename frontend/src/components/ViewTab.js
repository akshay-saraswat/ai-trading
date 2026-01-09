import React, { useState, useEffect } from 'react';
import axios from 'axios';

function ViewTab() {
  const [positions, setPositions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editingPosition, setEditingPosition] = useState(null);
  const [tpValue, setTpValue] = useState('');
  const [slValue, setSlValue] = useState('');

  useEffect(() => {
    loadPositions();
    // Refresh every 10 seconds
    const interval = setInterval(loadPositions, 10000);
    return () => clearInterval(interval);
  }, []);

  const loadPositions = async () => {
    try {
      const response = await axios.get('/api/positions');
      setPositions(response.data);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load positions');
    } finally {
      setLoading(false);
    }
  };

  const handleClosePosition = async (positionId, ticker) => {
    if (!window.confirm(`Close position for ${ticker}?`)) {
      return;
    }

    try {
      await axios.delete(`/api/positions/${positionId}`);
      await loadPositions();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to close position');
    }
  };

  const handleEditTP = (position) => {
    setEditingPosition({ id: position.position_id, type: 'tp' });
    // Default to 20% if not set
    setTpValue(position.take_profit !== null ? (position.take_profit * 100).toString() : '20');
  };

  const handleEditSL = (position) => {
    setEditingPosition({ id: position.position_id, type: 'sl' });
    // Default to 20% if not set
    setSlValue(position.stop_loss !== null ? (position.stop_loss * 100).toString() : '20');
  };

  const handleSaveTP = async (positionId) => {
    try {
      console.log('Saving TP:', { positionId, value: parseFloat(tpValue) });
      const response = await axios.put(`/api/positions/${positionId}/take-profit`, {
        value: parseFloat(tpValue)
      });
      console.log('TP update response:', response.data);
      await loadPositions();
      setEditingPosition(null);
      setError(null); // Clear any previous errors
    } catch (err) {
      console.error('TP update error:', err);
      const errorMsg = err.response?.data?.message || err.response?.data?.detail || err.message || 'Failed to update take-profit';
      setError(errorMsg);
      // Don't close the editor on error so user can retry
    }
  };

  const handleSaveSL = async (positionId) => {
    try {
      console.log('Saving SL:', { positionId, value: parseFloat(slValue) });
      const response = await axios.put(`/api/positions/${positionId}/stop-loss`, {
        value: parseFloat(slValue)
      });
      console.log('SL update response:', response.data);
      await loadPositions();
      setEditingPosition(null);
      setError(null); // Clear any previous errors
    } catch (err) {
      console.error('SL update error:', err);
      const errorMsg = err.response?.data?.message || err.response?.data?.detail || err.message || 'Failed to update stop-loss';
      setError(errorMsg);
      // Don't close the editor on error so user can retry
    }
  };

  if (loading) {
    return (
      <div className="view-container">
        <div className="loading">Loading positions...</div>
      </div>
    );
  }

  return (
    <div className="view-container">
      <div className="view-header">
        <div className="view-header-text">
          <h2>📈 Your Positions</h2>
          <p className="view-subtitle">Positions automatically update every 10 seconds. Click refresh for manual updates.</p>
        </div>
        <button onClick={loadPositions} className="refresh-button">
          🔄 Refresh
        </button>
      </div>

      {error && (
        <div className="error-message">
          ❌ {error}
        </div>
      )}

      {positions.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">📊</div>
          <p>No active positions</p>
          <small>Use the Chat tab to analyze stocks and place trades</small>
        </div>
      ) : (
        <div className="positions-list">
          {positions.map((position) => (
            <div key={position.position_id} className="position-card">
              <div className="position-header">
                <div className="position-ticker">
                  {position.ticker}
                  <span className="position-type">{position.decision}</span>
                  {position.source === 'robinhood' && (
                    <span className="position-source-badge" title="Opened in Robinhood app">🔗 RH</span>
                  )}
                </div>
                {position.pct_change !== null && (
                  <div className={`position-pnl ${position.pct_change >= 0 ? 'positive' : 'negative'}`}>
                    {position.pct_change >= 0 ? '+' : ''}{(position.pct_change * 100).toFixed(2)}%
                  </div>
                )}
              </div>

              <div className="position-details">
                <div className="detail-row">
                  <span className="detail-label">Strike</span>
                  <span className="detail-value">${position.strike}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Expiration</span>
                  <span className="detail-value">{position.expiration}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Entry Price</span>
                  <span className="detail-value">${position.entry_price.toFixed(2)}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Current Price</span>
                  <span className="detail-value">
                    {position.current_price ? `$${position.current_price.toFixed(2)}` : 'Loading...'}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Contracts</span>
                  <span className="detail-value">{position.contracts}</span>
                </div>
                {position.started_at && (
                  <div className="detail-row">
                    <span className="detail-label">Started</span>
                    <span className="detail-value">
                      {new Date(position.started_at).toLocaleDateString()}
                    </span>
                  </div>
                )}
                {position.source === 'robinhood' && (
                  <div className="detail-row">
                    <span className="detail-label">Source</span>
                    <span className="detail-value">Robinhood App</span>
                  </div>
                )}
              </div>

              <div className="position-tpsl">
                <div className="tpsl-item">
                  <span className="tpsl-label">Take Profit</span>
                  {editingPosition?.id === position.position_id && editingPosition?.type === 'tp' ? (
                    <div className="tpsl-edit">
                      <input
                        type="number"
                        value={tpValue}
                        onChange={(e) => setTpValue(e.target.value)}
                        min="5"
                        max="100"
                      />
                      <button onClick={() => handleSaveTP(position.position_id)} className="btn-save">✓</button>
                      <button onClick={() => setEditingPosition(null)} className="btn-cancel">✗</button>
                    </div>
                  ) : (
                    <span
                      className="tpsl-value clickable"
                      onClick={() => handleEditTP(position)}
                    >
                      {position.take_profit !== null
                        ? `+${(position.take_profit * 100).toFixed(0)}% ✏️`
                        : 'Set TP ➕'}
                    </span>
                  )}
                </div>
                <div className="tpsl-item">
                  <span className="tpsl-label">Stop Loss</span>
                  {editingPosition?.id === position.position_id && editingPosition?.type === 'sl' ? (
                    <div className="tpsl-edit">
                      <input
                        type="number"
                        value={slValue}
                        onChange={(e) => setSlValue(e.target.value)}
                        min="1"
                        max="50"
                      />
                      <button onClick={() => handleSaveSL(position.position_id)} className="btn-save">✓</button>
                      <button onClick={() => setEditingPosition(null)} className="btn-cancel">✗</button>
                    </div>
                  ) : (
                    <span
                      className="tpsl-value clickable"
                      onClick={() => handleEditSL(position)}
                    >
                      {position.stop_loss !== null
                        ? `-${(position.stop_loss * 100).toFixed(0)}% ✏️`
                        : 'Set SL ➕'}
                    </span>
                  )}
                </div>
              </div>

              <button
                className="btn-close-position"
                onClick={() => handleClosePosition(position.position_id, position.ticker)}
              >
                Close Position
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default ViewTab;
