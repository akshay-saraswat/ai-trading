import React, { useState, useRef, useEffect } from 'react';

function InsightsTab({ robinhoodAuthenticated = false }) {
  // Use localStorage to persist insights data across tab switches
  const [insights, setInsights] = useState(() => {
    try {
      const saved = localStorage.getItem('insightsData');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [tradingStock, setTradingStock] = useState(null);
  const [contracts, setContracts] = useState('');
  const [loadingProgress, setLoadingProgress] = useState({ current: 0, total: 0 });
  const [screenerType, setScreenerType] = useState(() => {
    // Persist screener type across page reloads
    return localStorage.getItem('screenerType') || 'most_actives';
  });
  const abortControllerRef = useRef(null);
  const isMountedRef = useRef(true);
  const insightsRef = useRef(insights);

  // Keep ref in sync with insights state
  useEffect(() => {
    insightsRef.current = insights;
  }, [insights]);

  // Save insights to localStorage whenever they change
  useEffect(() => {
    if (insights.length > 0) {
      localStorage.setItem('insightsData', JSON.stringify(insights));
    }
  }, [insights]);

  // Save screener type to localStorage whenever it changes
  useEffect(() => {
    localStorage.setItem('screenerType', screenerType);
  }, [screenerType]);

  // Track mount status and restore loading state if fetch in progress
  useEffect(() => {
    isMountedRef.current = true;

    // Ensure ref is synced with initial insights from localStorage
    insightsRef.current = insights;

    // Check localStorage to see if a fetch is in progress
    const fetchInProgress = localStorage.getItem('insightsFetchInProgress') === 'true';

    // Check if the fetch has been in progress for too long (over 5 minutes = stale)
    let isStaleFetch = false;

    if (fetchInProgress) {
      const lastUpdateTime = localStorage.getItem('insightsFetchLastUpdate');

      // If no lastUpdateTime exists, or if it's been too long, it's stale
      if (!lastUpdateTime) {
        isStaleFetch = true;
        console.warn('Detected stale fetch operation (no timestamp), clearing...');
        localStorage.removeItem('insightsFetchInProgress');
        localStorage.removeItem('insightsLoadingProgress');
        localStorage.removeItem('insightsFetchLastUpdate');
      } else {
        const timeSinceUpdate = Date.now() - parseInt(lastUpdateTime);
        // If no update in 5 minutes, consider it stale
        if (timeSinceUpdate > 5 * 60 * 1000) {
          isStaleFetch = true;
          console.warn('Detected stale fetch operation (timeout), clearing...');
          localStorage.removeItem('insightsFetchInProgress');
          localStorage.removeItem('insightsLoadingProgress');
          localStorage.removeItem('insightsFetchLastUpdate');
        }
      }
    }

    if (fetchInProgress && !isStaleFetch) {
      setLoading(true);
      // Try to restore loading progress from localStorage
      try {
        const savedProgress = localStorage.getItem('insightsLoadingProgress');
        if (savedProgress) {
          setLoadingProgress(JSON.parse(savedProgress));
        }
      } catch {
        // Ignore errors
      }
    }

    // Poll localStorage for updates while fetch is in progress
    let pollInterval = null;
    if (fetchInProgress) {
      pollInterval = setInterval(() => {
        try {
          // Check if fetch is still in progress
          const stillFetching = localStorage.getItem('insightsFetchInProgress') === 'true';
          if (!stillFetching) {
            clearInterval(pollInterval);
            setLoading(false);
            setLoadingProgress({ current: 0, total: 0 });
            return;
          }

          // Update insights from localStorage
          const savedInsights = localStorage.getItem('insightsData');
          if (savedInsights) {
            const parsed = JSON.parse(savedInsights);
            setInsights(parsed);
          }

          // Update progress from localStorage
          const savedProgress = localStorage.getItem('insightsLoadingProgress');
          if (savedProgress) {
            setLoadingProgress(JSON.parse(savedProgress));
          }
        } catch (error) {
          console.error('Error polling insights:', error);
        }
      }, 500); // Poll every 500ms
    }

    return () => {
      isMountedRef.current = false;
      if (pollInterval) {
        clearInterval(pollInterval);
      }
      // Don't abort the fetch when unmounting - let it continue in background
      // Only abort if user explicitly navigates away permanently
    };
  }, []);

  const fetchInsightsProgressively = async () => {
    // Check if fetch is already in progress (across component mounts)
    const alreadyFetching = localStorage.getItem('insightsFetchInProgress') === 'true';
    if (loading || alreadyFetching) return;

    setLoading(true);
    localStorage.setItem('insightsFetchInProgress', 'true');
    localStorage.setItem('insightsFetchLastUpdate', Date.now().toString());
    setError(null);
    setInsights([]); // Clear previous insights
    setLoadingProgress({ current: 0, total: 0 });
    localStorage.removeItem('insightsLoadingProgress'); // Clear old progress
    localStorage.removeItem('insightsData'); // Clear old insights data

    // Create abort controller for cleanup
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    try {
      // Check if running in development (React dev server on port 3000)
      const isDevelopment = window.location.port === '3000';
      const baseUrl = isDevelopment ? 'http://localhost:8000' : '';

      // Get auth token for personalized results
      const token = localStorage.getItem('auth_token');
      const headers = {
        'Content-Type': 'application/json',
      };

      // Add Authorization header if token exists
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      // Step 1: Get list of tickers with selected screener type
      const tickersResponse = await fetch(`${baseUrl}/api/insights/tickers?screener=${screenerType}`, {
        headers,
        signal
      });
      const tickersData = await tickersResponse.json();

      if (!tickersData.success || !tickersData.tickers) {
        throw new Error('Failed to fetch tickers');
      }

      const tickers = tickersData.tickers;
      const progress = { current: 0, total: tickers.length };
      if (isMountedRef.current) {
        setLoadingProgress(progress);
        localStorage.setItem('insightsLoadingProgress', JSON.stringify(progress));
      }

      // Step 2: Analyze tickers one by one
      for (let i = 0; i < tickers.length; i++) {
        if (signal.aborted) break;

        const ticker = tickers[i];

        try {
          const analyzeResponse = await fetch(`${baseUrl}/api/insights/analyze/${ticker}`, {
            headers,
            signal
          });
          const analyzeData = await analyzeResponse.json();

          if (analyzeData.success && analyzeData.insight) {
            // Add the insight to the list immediately using ref to avoid closure issues
            const updatedInsights = [...insightsRef.current, analyzeData.insight];

            // Update the ref immediately so next iteration has the latest data
            insightsRef.current = updatedInsights;

            // Always save to localStorage for persistence and polling
            localStorage.setItem('insightsData', JSON.stringify(updatedInsights));

            // Update React state only if component is still mounted
            if (isMountedRef.current) {
              setInsights(updatedInsights);
            }

            // Update progress
            const newProgress = { current: i + 1, total: tickers.length };
            localStorage.setItem('insightsLoadingProgress', JSON.stringify(newProgress));
            localStorage.setItem('insightsFetchLastUpdate', Date.now().toString());

            if (isMountedRef.current) {
              setLoadingProgress(newProgress);
            }
          }
        } catch (err) {
          // Skip failed tickers but continue with others
          if (err.name !== 'AbortError') {
            console.error(`Error analyzing ${ticker}:`, err);
          }
        }
      }

    } catch (err) {
      if (err.name !== 'AbortError' && isMountedRef.current) {
        setError('Error connecting to backend: ' + err.message);
        console.error('Error fetching insights:', err);
      }
    } finally {
      // Mark fetch as complete
      localStorage.removeItem('insightsFetchInProgress');
      localStorage.removeItem('insightsLoadingProgress');
      localStorage.removeItem('insightsFetchLastUpdate');

      if (isMountedRef.current) {
        setLoading(false);
        setLoadingProgress({ current: 0, total: 0 });
      }
      abortControllerRef.current = null;
    }
  };

  const handleTrade = (insight) => {
    setTradingStock(insight);
    setContracts('');
  };

  const handleSubmitTrade = async () => {
    if (!contracts || parseInt(contracts) < 1) {
      alert('Please enter a valid number of contracts');
      return;
    }

    const numContracts = parseInt(contracts);

    // Check max contracts
    if (numContracts > tradingStock.option.max_contracts) {
      alert(`Maximum ${tradingStock.option.max_contracts} contracts allowed with current budget`);
      return;
    }

    const totalCost = (tradingStock.option.limit_price * numContracts * 100).toFixed(2);

    const confirmed = window.confirm(
      `Trade Summary for ${tradingStock.ticker}\n\n` +
      `Decision: ${tradingStock.decision}\n` +
      `Strike: $${tradingStock.option.strike}\n` +
      `Expiration: ${tradingStock.option.expiration}\n` +
      `Contracts: ${numContracts}\n` +
      `Price per contract: $${tradingStock.option.limit_price.toFixed(2)}\n` +
      `Total cost: $${totalCost}\n\n` +
      `Confirm this trade?`
    );

    if (confirmed) {
      try {
        // Check if running in development (React dev server on port 3000)
        const isDevelopment = window.location.port === '3000';
        const baseUrl = isDevelopment ? 'http://localhost:8000' : '';

        const token = localStorage.getItem('auth_token');
        const headers = {
          'Content-Type': 'application/json',
        };

        // Add Authorization header if token exists
        if (token) {
          headers['Authorization'] = `Bearer ${token}`;
        }

        // Place the trade via backend API
        const response = await fetch(`${baseUrl}/api/trade/place-option`, {
          method: 'POST',
          headers: headers,
          body: JSON.stringify({
            option_id: tradingStock.option.option_id,
            ticker: tradingStock.ticker,
            decision: tradingStock.decision,
            contracts: numContracts,
            strike: tradingStock.option.strike,
            expiration: tradingStock.option.expiration,
            limit_price: tradingStock.option.limit_price,
            strategy_used: tradingStock.strategy_used || 'none',
            exit_targets: tradingStock.exit_targets
          })
        });

        const data = await response.json();

        if (data.success) {
          alert(`✅ ${data.message}\n\nOrder ID: ${data.order_id}\nTotal Cost: $${data.details.total_cost.toFixed(2)}`);
        } else {
          alert(`❌ Trade failed:\n\n${data.message || 'Unknown error occurred'}`);
        }
      } catch (err) {
        alert(`❌ Error placing trade:\n\n${err.message}`);
        console.error('Trade placement error:', err);
      } finally {
        setTradingStock(null);
        setContracts('');
      }
    }
  };

  const getDecisionBadgeClass = (decision) => {
    if (decision === 'BUY_CALL') return 'badge-bullish';
    if (decision === 'BUY_PUT') return 'badge-bearish';
    return 'badge-neutral';
  };

  const formatDecision = (decision) => {
    return decision.replace('_', ' ');
  };

  const formatStrategy = (strategy) => {
    const strategyMap = {
      'mean_reversion': 'Mean Reversion',
      'momentum': 'Momentum',
      'trend_following': 'Trend Following',
      'covered_call': 'Covered Call',
      'cash_secured_put': 'Cash-Secured Put',
      'bull_call_spread': 'Bull Call Spread',
      'bear_put_spread': 'Bear Put Spread',
      'straddle': 'Straddle',
      'none': 'None'
    };
    return strategyMap[strategy] || strategy;
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.7) return '#4caf50';
    if (confidence >= 0.5) return '#ff9800';
    return '#f44336';
  };

  const getScreenerLabel = (type) => {
    const labels = {
      'most_actives': 'Most Active',
      'most_shorted_stocks': 'Most Shorted',
      'day_gainers': 'Day Gainers',
      'day_losers': 'Day Losers',
      'growth_technology_stocks': 'Growth Technology',
      'trending_tickers': 'Trending'
    };
    return labels[type] || 'Most Active';
  };

  const handleScreenerChange = (e) => {
    const newScreener = e.target.value;
    setScreenerType(newScreener);
  };

  if (error) {
    return (
      <div className="insights-container">
        <div className="view-header">
          <div className="view-header-text">
            <h2>🔍 Stock Screener</h2>
            <p className="view-subtitle">Top 10 Most Active Stocks with AI Analysis</p>
          </div>
        </div>
        <div className="error-state">
          <p>{error}</p>
          <button onClick={fetchInsightsProgressively} className="btn-primary">Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className="insights-container">
      <div className="view-header">
        <div className="view-header-text">
          <h2>🔍 Stock Screener</h2>
          <p className="view-subtitle">Top 10 {getScreenerLabel(screenerType)} Stocks with AI Analysis</p>
        </div>
        <div className="view-header-controls">
          <select
            value={screenerType}
            onChange={handleScreenerChange}
            className="screener-dropdown"
            disabled={loading}
            title="Select stock screener"
          >
            <option value="most_actives">Most Active</option>
            <option value="trending_tickers">Trending</option>
            <option value="day_gainers">Day Gainers</option>
            <option value="day_losers">Day Losers</option>
            <option value="most_shorted_stocks">Most Shorted</option>
            <option value="growth_technology_stocks">Growth Technology</option>
          </select>
          <button
            onClick={fetchInsightsProgressively}
            className="refresh-button"
            disabled={loading}
            title={loading ? "Analysis in progress..." : "Refresh insights"}
          >
            🔄 Refresh
          </button>
        </div>
      </div>

      {insights.length === 0 && !loading ? (
        <div className="empty-state">
          <div className="empty-state-icon">🔍</div>
          <p>No stocks screened yet</p>
          <small>Click the Refresh button to analyze the top 10 most active stocks</small>
        </div>
      ) : (
        <>
          <div className="insights-grid">
            {insights.map((insight, index) => (
              <div key={index} className="insight-card">
                <div className="insight-header">
                  <div className="ticker-price">
                    <h3 className="ticker">{insight.ticker}</h3>
                    <p className="price">${insight.current_price.toFixed(2)}</p>
                  </div>
                  <div className="insight-badges">
                    <div className={`decision-badge ${getDecisionBadgeClass(insight.decision)}`}>
                      {formatDecision(insight.decision)}
                    </div>
                    {insight.strategy_used && insight.strategy_used !== 'none' && (
                      <span className="strategy-badge">Strategy: {formatStrategy(insight.strategy_used)}</span>
                    )}
                  </div>
                </div>

                <div className="confidence-bar-container">
                  <div className="confidence-label">
                    <span>Confidence</span>
                    <span className="confidence-value">{(insight.confidence * 100).toFixed(1)}%</span>
                  </div>
                  <div className="confidence-bar">
                    <div
                      className="confidence-fill"
                      style={{
                        width: `${insight.confidence * 100}%`,
                        backgroundColor: getConfidenceColor(insight.confidence)
                      }}
                    ></div>
                  </div>
                </div>

                <div className="insight-reasoning">
                  <p>{insight.reasoning}</p>
                  {insight.exit_targets && insight.decision !== 'NOTHING' && (
                    <div className="exit-targets-inline">
                      <div className="exit-targets-grid">
                        <div className="exit-target-item">
                          <span className="target-label">Take Profit</span>
                          <span className="target-value profit">+{(insight.exit_targets.take_profit_pct * 100).toFixed(0)}%</span>
                        </div>
                        <div className="exit-target-item">
                          <span className="target-label">Stop Loss</span>
                          <span className="target-value loss">-{(insight.exit_targets.stop_loss_pct * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                      {insight.exit_targets.rationale && (
                        <p className="exit-rationale">{insight.exit_targets.rationale}</p>
                      )}
                    </div>
                  )}
                </div>

                <div className="insight-indicators">
                  <div className="indicator-item">
                    <span className="indicator-label">RSI</span>
                    <span className="indicator-value">
                      {insight.indicators.RSI ? insight.indicators.RSI.toFixed(2) : 'N/A'}
                    </span>
                  </div>
                  <div className="indicator-item">
                    <span className="indicator-label">SMA 50</span>
                    <span className="indicator-value">
                      {insight.indicators.SMA_50 ? `$${insight.indicators.SMA_50.toFixed(2)}` : 'N/A'}
                    </span>
                  </div>
                  <div className="indicator-item">
                    <span className="indicator-label">SMA 200</span>
                    <span className="indicator-value">
                      {insight.indicators.SMA_200 ? `$${insight.indicators.SMA_200.toFixed(2)}` : 'N/A'}
                    </span>
                  </div>
                </div>

                {insight.option && (
                  <div className="insight-option">
                    <h4>Recommended Option</h4>
                    <div className="option-details">
                      <div className="option-row">
                        <span>Strike:</span>
                        <span>${insight.option.strike}</span>
                      </div>
                      <div className="option-row">
                        <span>Expiration:</span>
                        <span>{insight.option.expiration}</span>
                      </div>
                      <div className="option-row">
                        <span>Limit Price:</span>
                        <span>${insight.option.limit_price.toFixed(2)}</span>
                      </div>
                    </div>
                    {robinhoodAuthenticated ? (
                      <button
                        className="btn-trade"
                        onClick={() => handleTrade(insight)}
                      >
                        Trade
                      </button>
                    ) : (
                      <div style={{
                        padding: '12px',
                        background: 'rgba(59, 130, 246, 0.1)',
                        border: '1px solid rgba(59, 130, 246, 0.3)',
                        borderRadius: '8px',
                        color: 'var(--text-secondary)',
                        fontSize: '14px',
                        textAlign: 'center'
                      }}>
                        Login to Robinhood to trade
                      </div>
                    )}
                  </div>
                )}

                {!insight.option && insight.decision !== 'HOLD' && (
                  <div className="insight-no-option">
                    <p>No suitable option available</p>
                  </div>
                )}
              </div>
            ))}
          </div>

          {loading && (
            <div className="loading-spinner-bottom">
              <div className="spinner"></div>
              <p>
                Analyzing stocks... {loadingProgress.current > 0 && loadingProgress.total > 0
                  ? `(${loadingProgress.current}/${loadingProgress.total})`
                  : ''}
              </p>
            </div>
          )}
        </>
      )}

      {tradingStock && (
        <div className="trade-modal-overlay" onClick={() => setTradingStock(null)}>
          <div className="trade-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Place Trade: {tradingStock.ticker}</h3>
              <button className="modal-close" onClick={() => setTradingStock(null)}>
                &times;
              </button>
            </div>

            <div className="modal-body">
              <div className="trade-summary">
                <div className="summary-row">
                  <span>Decision:</span>
                  <span className="summary-value">{formatDecision(tradingStock.decision)}</span>
                </div>
                <div className="summary-row">
                  <span>Strike:</span>
                  <span className="summary-value">${tradingStock.option.strike}</span>
                </div>
                <div className="summary-row">
                  <span>Expiration:</span>
                  <span className="summary-value">{tradingStock.option.expiration}</span>
                </div>
                <div className="summary-row">
                  <span>Price per contract:</span>
                  <span className="summary-value">${tradingStock.option.limit_price.toFixed(2)}</span>
                </div>
              </div>

              <div className="trade-input-group">
                <label htmlFor="contracts">Number of Contracts:</label>
                <input
                  id="contracts"
                  type="number"
                  min="1"
                  max="100"
                  value={contracts}
                  onChange={(e) => setContracts(e.target.value)}
                  placeholder="Enter number of contracts"
                  className="contracts-input"
                />
              </div>

              {contracts && parseInt(contracts) > 0 && (
                <div className="total-cost">
                  <span>Total Cost:</span>
                  <span className="cost-value">
                    ${(tradingStock.option.limit_price * parseInt(contracts) * 100).toFixed(2)}
                  </span>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button className="btn-cancel" onClick={() => setTradingStock(null)}>
                Cancel
              </button>
              <button className="btn-confirm" onClick={handleSubmitTrade}>
                Confirm Trade
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default InsightsTab;
