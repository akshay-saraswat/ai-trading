import React, { useState, useEffect } from 'react';

function SettingsTab() {
  const [settings, setSettings] = useState({
    indicators: {
      RSI: true,
      MACD: true,
      Stochastic: true,
      SMA_20: true,
      SMA_50: true,
      SMA_200: true,
      EMA_12: true,
      EMA_26: true,
      Bollinger_Bands: true,
      ATR: true,
      ADX: true,
      OBV: true,
    },
    riskManagement: {
      default_take_profit: 20,
      default_stop_loss: 20,
      max_position_size: 1000,
      skip_market_schedule_check: false,
      block_first_hour_trading: true,
    }
  });

  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');

  // Load settings on mount
  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      // Check if running in development (React dev server on port 3000)
      const isDevelopment = window.location.port === '3000';
      const baseUrl = isDevelopment ? 'http://localhost:8000' : '';
      const response = await fetch(`${baseUrl}/api/settings`);
      if (response.ok) {
        const data = await response.json();
        setSettings(data);
      }
    } catch (error) {
      console.error('Error fetching settings:', error);
    }
  };

  const handleIndicatorToggle = (indicator) => {
    setSettings(prev => ({
      ...prev,
      indicators: {
        ...prev.indicators,
        [indicator]: !prev.indicators[indicator]
      }
    }));
  };


  const handleRiskChange = (field, value) => {
    setSettings(prev => ({
      ...prev,
      riskManagement: {
        ...prev.riskManagement,
        [field]: parseFloat(value)
      }
    }));
  };

  const saveSettings = async () => {
    setIsSaving(true);
    setSaveMessage('');

    try {
      // Check if running in development (React dev server on port 3000)
      const isDevelopment = window.location.port === '3000';
      const baseUrl = isDevelopment ? 'http://localhost:8000' : '';
      const response = await fetch(`${baseUrl}/api/settings`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(settings),
      });

      if (response.ok) {
        setSaveMessage('✅ Settings saved successfully!');
      } else {
        setSaveMessage('❌ Failed to save settings');
      }
    } catch (error) {
      console.error('Error saving settings:', error);
      setSaveMessage('❌ Error saving settings');
    } finally {
      setIsSaving(false);
      setTimeout(() => setSaveMessage(''), 3000);
    }
  };

  const indicatorDescriptions = {
    RSI: 'Relative Strength Index - Measures overbought/oversold conditions (0-100)',
    MACD: 'Moving Average Convergence Divergence - Trend momentum indicator',
    Stochastic: 'Stochastic Oscillator - Momentum indicator comparing close to price range',
    SMA_20: '20-day Simple Moving Average - Very short-term trend line',
    SMA_50: '50-day Simple Moving Average - Short-term trend line',
    SMA_200: '200-day Simple Moving Average - Long-term trend line',
    EMA_12: '12-day Exponential Moving Average - Fast-reacting short-term trend',
    EMA_26: '26-day Exponential Moving Average - Medium-term trend indicator',
    Bollinger_Bands: 'Bollinger Bands - Volatility bands showing price extremes',
    ATR: 'Average True Range - Measures market volatility',
    ADX: 'Average Directional Index - Measures trend strength (not direction)',
    OBV: 'On Balance Volume - Volume-based momentum indicator',
  };


  return (
    <div className="settings-container">
      <div className="settings-header">
        <h2>⚙️ Bot Settings</h2>
        <p className="settings-subtitle">Customize indicators and risk management for trade analysis</p>
      </div>

      <div className="settings-content">
        {/* Technical Indicators Section */}
        <div className="settings-section">
          <h3>📊 Technical Indicators</h3>
          <p className="section-description">Select which indicators the bot should analyze</p>

          <div className="settings-grid">
            {Object.keys(settings.indicators).map(indicator => (
              <div key={indicator} className="setting-item">
                <label className="setting-label">
                  <input
                    type="checkbox"
                    checked={settings.indicators[indicator]}
                    onChange={() => handleIndicatorToggle(indicator)}
                    className="setting-checkbox"
                  />
                  <div className="setting-info">
                    <span className="setting-name">{indicator.replace('_', ' ')}</span>
                    <span className="setting-description">
                      {indicatorDescriptions[indicator]}
                    </span>
                  </div>
                </label>
              </div>
            ))}
          </div>
        </div>

        {/* Risk Management Section */}
        <div className="settings-section">
          <h3>🛡️ Risk Management</h3>
          <p className="section-description">Configure default risk parameters</p>

          <div className="risk-settings">
            <div className="risk-item">
              <label className="risk-label">
                <span>Default Take Profit (%)</span>
                <input
                  type="number"
                  min="5"
                  max="100"
                  value={settings.riskManagement.default_take_profit}
                  onChange={(e) => handleRiskChange('default_take_profit', e.target.value)}
                  className="risk-input"
                />
              </label>
              <span className="risk-description">Sell when profit reaches this percentage</span>
            </div>

            <div className="risk-item">
              <label className="risk-label">
                <span>Default Stop Loss (%)</span>
                <input
                  type="number"
                  min="1"
                  max="50"
                  value={settings.riskManagement.default_stop_loss}
                  onChange={(e) => handleRiskChange('default_stop_loss', e.target.value)}
                  className="risk-input"
                />
              </label>
              <span className="risk-description">Sell when loss reaches this percentage</span>
            </div>

            <div className="risk-item">
              <label className="risk-label">
                <span>Max Position Size ($)</span>
                <input
                  type="number"
                  min="100"
                  max="50000"
                  step="100"
                  value={settings.riskManagement.max_position_size}
                  onChange={(e) => handleRiskChange('max_position_size', e.target.value)}
                  className="risk-input"
                />
              </label>
              <span className="risk-description">Maximum amount to invest in a single trade</span>
            </div>

            <div className="risk-item">
              <label className="risk-label">
                <span>Skip Market Hours Check</span>
                <div
                  className={`toggle-switch ${settings.riskManagement.skip_market_schedule_check ? 'active' : ''}`}
                  onClick={() => setSettings(prev => ({
                    ...prev,
                    riskManagement: {
                      ...prev.riskManagement,
                      skip_market_schedule_check: !prev.riskManagement.skip_market_schedule_check
                    }
                  }))}
                >
                  <div className="toggle-slider"></div>
                </div>
              </label>
              <span className="risk-description">Allow trading outside normal market hours (for testing)</span>
            </div>

            <div className="risk-item">
              <label className="risk-label">
                <span>Block First Hour Trading</span>
                <div
                  className={`toggle-switch ${settings.riskManagement.block_first_hour_trading ? 'active' : ''}`}
                  onClick={() => setSettings(prev => ({
                    ...prev,
                    riskManagement: {
                      ...prev.riskManagement,
                      block_first_hour_trading: !prev.riskManagement.block_first_hour_trading
                    }
                  }))}
                >
                  <div className="toggle-slider"></div>
                </div>
              </label>
              <span className="risk-description">Block all automated trades during the first hour after market open (9:30-10:30 AM ET) to avoid high volatility</span>
            </div>
          </div>
        </div>

        {/* Save Button */}
        <div className="settings-actions">
          <button
            onClick={saveSettings}
            disabled={isSaving}
            className="save-button"
          >
            {isSaving ? 'Saving...' : '💾 Save Settings'}
          </button>
          {saveMessage && (
            <div className={`save-message ${saveMessage.includes('✅') ? 'success' : 'error'}`}>
              {saveMessage}
            </div>
          )}
        </div>

        {/* Info Box */}
        <div className="settings-info-box">
          <strong>ℹ️ Note:</strong> Changes will apply to all future trade analyses.
          Active positions will continue using their original settings.
        </div>
      </div>
    </div>
  );
}

export default SettingsTab;
