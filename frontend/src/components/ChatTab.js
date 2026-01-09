import React, { useState, useEffect, useRef } from 'react';
import wsManager from '../utils/websocket';

function ChatTab() {
  // Persist messages across tab switches
  const [messages, setMessages] = useState(() => {
    try {
      const saved = localStorage.getItem('chatMessages');
      if (saved) {
        const parsed = JSON.parse(saved);
        // Restore Date objects for timestamps
        return parsed.map(msg => ({
          ...msg,
          timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date()
        }));
      }
      return [];
    } catch {
      return [];
    }
  });
  const [inputValue, setInputValue] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [contractCount, setContractCount] = useState(1);
  const [isPlacingTrade, setIsPlacingTrade] = useState(false);
  const messagesEndRef = useRef(null);

  // Auto-scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Save messages to localStorage whenever they change
  useEffect(() => {
    if (messages.length > 0) {
      localStorage.setItem('chatMessages', JSON.stringify(messages));
    }
  }, [messages]);

  // Use global WebSocket manager
  useEffect(() => {
    // Connect to WebSocket (will reuse existing connection if available)
    wsManager.connect();

    // Subscribe to messages
    const unsubscribeMessages = wsManager.onMessage((message) => {
      console.log('Chat received message:', message);
      if (message.data) {
        console.log('Message data:', message.data);
        console.log('Option recommendation:', message.data.option_recommendation);
      }
      setMessages(prev => [...prev, message]);
      setIsTyping(false);
    });

    // Subscribe to connection status
    const unsubscribeStatus = wsManager.onStatusChange((connected) => {
      setIsConnected(connected);
    });

    // Cleanup: unsubscribe but don't disconnect (keeps WebSocket alive)
    return () => {
      unsubscribeMessages();
      unsubscribeStatus();
    };
  }, []);

  const sendMessage = (e) => {
    e.preventDefault();

    if (!inputValue.trim() || !isConnected) return;

    // Get or create persistent session ID
    let sessionId = localStorage.getItem('chatSessionId');
    if (!sessionId) {
      sessionId = `session_${Date.now()}_${Math.random().toString(36).substring(7)}`;
      localStorage.setItem('chatSessionId', sessionId);
    }

    // Send message via WebSocket manager with session ID
    const sent = wsManager.send({
      message: inputValue,
      sessionId: sessionId
    });

    if (sent) {
      setInputValue('');
      setIsTyping(true);
    }
  };

  const getMessageClassName = (type) => {
    if (type === 'user') return 'message message-user';
    if (type === 'system') return 'message message-system';
    return 'message message-assistant';
  };

  const formatMessageContent = (content) => {
    if (!content) return '';
    return content.split('\n').map((line, i) => (
      <span key={i}>
        {line}
        {i < content.split('\n').length - 1 && <br />}
      </span>
    ));
  };

  const handlePlaceOptionTrade = async (option) => {
    const contracts = parseInt(contractCount);
    if (isNaN(contracts) || contracts < 1) {
      alert('Please enter a valid number of contracts (minimum 1)');
      return;
    }

    if (contracts > option.max_contracts) {
      alert(`Maximum ${option.max_contracts} contracts allowed with current budget`);
      return;
    }

    if (!window.confirm(`Place order for ${contracts} contract(s) of ${option.ticker} ${option.strike} ${option.type}?\n\nTotal cost: $${(option.limit_price * contracts * 100).toFixed(2)}`)) {
      return;
    }

    setIsPlacingTrade(true);
    try {
      const isDevelopment = window.location.port === '3000';
      const baseUrl = isDevelopment ? 'http://localhost:8000' : '';

      const response = await fetch(`${baseUrl}/api/trade/place-option`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          option_id: option.option_id,
          ticker: option.ticker,
          decision: option.type,
          contracts: contracts,
          strike: option.strike,
          expiration: option.expiration,
          limit_price: option.limit_price
        })
      });

      const result = await response.json();

      if (result.success) {
        alert(`✅ ${result.message}\n\nOrder ID: ${result.order_id}\nTotal Cost: $${result.details.total_cost.toFixed(2)}`);
        setContractCount(1);
      } else {
        alert(`❌ Failed to place order: ${result.message}`);
      }
    } catch (error) {
      alert(`❌ Error placing trade: ${error.message}`);
    } finally {
      setIsPlacingTrade(false);
    }
  };

  const renderAnalysisData = (data) => {
    if (!data) return null;

    return (
      <div className="analysis-data">
        <div className="analysis-header">
          <strong>{data.ticker}</strong> - ${data.current_price?.toFixed(2)}
        </div>
        <div className="analysis-decision">
          <span className={`decision-badge decision-${data.decision?.toLowerCase()}`}>
            {data.decision}
          </span>
          <span className="confidence-badge">
            Confidence: {(data.confidence * 100).toFixed(1)}%
          </span>
          {data.strategy_used && data.strategy_used !== 'none' && (
            <span className="strategy-badge">
              Strategy: {data.strategy_used.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
            </span>
          )}
        </div>
        <div className="analysis-reasoning">
          {data.reasoning}
        </div>
        {data.indicators && (
          <div className="analysis-indicators">
            <strong>Technical Indicators:</strong>
            <ul>
              {data.indicators.RSI && <li>RSI: {data.indicators.RSI.toFixed(2)}</li>}
              {data.indicators.SMA_50 && <li>SMA 50: ${data.indicators.SMA_50.toFixed(2)}</li>}
              {data.indicators.SMA_200 && <li>SMA 200: ${data.indicators.SMA_200.toFixed(2)}</li>}
            </ul>
          </div>
        )}
        {data.option_recommendation && (
          <div className="option-recommendation">
            <div className="option-recommendation-header">
              <strong>📈 Option Trade Setup</strong>
            </div>
            <div className="option-details-grid">
              <div className="option-detail-item">
                <label>Type</label>
                <span className={`option-type-badge ${data.option_recommendation.type.toLowerCase().replace('_', '-')}`}>
                  {data.option_recommendation.type}
                </span>
              </div>
              <div className="option-detail-item">
                <label>Strike Price</label>
                <span className="option-value">${data.option_recommendation.strike.toFixed(2)}</span>
              </div>
              <div className="option-detail-item">
                <label>Expiration</label>
                <span className="option-value">{data.option_recommendation.expiration}</span>
              </div>
              <div className="option-detail-item">
                <label>Market Price</label>
                <span className="option-value">${data.option_recommendation.market_price.toFixed(2)}</span>
              </div>
              <div className="option-detail-item">
                <label>Limit Price</label>
                <span className="option-value option-limit-price">${data.option_recommendation.limit_price.toFixed(2)}</span>
              </div>
              <div className="option-detail-item">
                <label>Cost/Contract</label>
                <span className="option-value">${data.option_recommendation.cost_per_contract.toFixed(2)}</span>
              </div>
            </div>

            {/* Exit Targets */}
            {data.option_recommendation.exit_targets && (
              <div className="option-entry-exit-section">
                {data.option_recommendation.exit_targets && (
                  <div className="exit-targets-card">
                    <div className="entry-exit-header">
                      <span className="entry-exit-icon">🚪</span>
                      <strong>Exit Targets</strong>
                    </div>
                    <div className="exit-targets-grid">
                      {data.option_recommendation.exit_targets.take_profit && (
                        <div className="exit-target-item take-profit">
                          <div className="exit-target-label">
                            <span className="target-icon">✅</span> Take Profit
                          </div>
                          <div className="price-display profit-price">
                            ${data.option_recommendation.exit_targets.take_profit.price?.toFixed(2)}
                            <span className="pct-badge profit-pct">{data.option_recommendation.exit_targets.take_profit.pct}</span>
                          </div>
                          <div className="rationale-text">
                            {data.option_recommendation.exit_targets.take_profit.rationale}
                          </div>
                        </div>
                      )}
                      {data.option_recommendation.exit_targets.stop_loss && (
                        <div className="exit-target-item stop-loss">
                          <div className="exit-target-label">
                            <span className="target-icon">🛑</span> Stop Loss
                          </div>
                          <div className="price-display loss-price">
                            ${data.option_recommendation.exit_targets.stop_loss.price?.toFixed(2)}
                            <span className="pct-badge loss-pct">{data.option_recommendation.exit_targets.stop_loss.pct}</span>
                          </div>
                          <div className="rationale-text">
                            {data.option_recommendation.exit_targets.stop_loss.rationale}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
            <div className="option-trade-controls">
              {data.option_recommendation.max_contracts > 0 ? (
                <>
                  <div className="contract-input-group">
                    <label htmlFor="contract-count">Number of Contracts (max {data.option_recommendation.max_contracts}):</label>
                    <input
                      id="contract-count"
                      type="number"
                      min="1"
                      max={data.option_recommendation.max_contracts}
                      value={contractCount}
                      onChange={(e) => setContractCount(e.target.value)}
                      className="contract-input"
                    />
                  </div>
                  <div className="total-cost-display">
                    Total Cost: ${(data.option_recommendation.limit_price * contractCount * 100).toFixed(2)}
                  </div>
                  <button
                    className="place-trade-button"
                    onClick={() => handlePlaceOptionTrade(data.option_recommendation)}
                    disabled={isPlacingTrade || contractCount < 1 || contractCount > data.option_recommendation.max_contracts}
                  >
                    {isPlacingTrade ? '⏳ Placing Order...' : '✅ Place Option Trade'}
                  </button>
                </>
              ) : (
                <div className="budget-warning">
                  <div className="warning-icon">⚠️</div>
                  <div className="warning-content">
                    <strong>Insufficient Budget</strong>
                    <p>
                      This option costs <strong>${data.option_recommendation.cost_per_contract.toFixed(2)}</strong> per contract,
                      but your budget is only <strong>$1,000</strong>.
                    </p>
                    <p className="warning-suggestion">
                      💡 Increase MAX_POSITION_SIZE in settings to at least ${Math.ceil(data.option_recommendation.cost_per_contract / 100) * 100} to trade this option.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
        {data.trade_recommendation && (
          <div className="trade-recommendation">
            <div className="trade-recommendation-header">
              <strong>📊 Stock Trade Setup</strong>
            </div>
            <div className="trade-recommendation-grid">
              <div className="trade-rec-item">
                <label>Entry Price</label>
                <span className="trade-rec-value">${data.trade_recommendation.entry_price.toFixed(2)}</span>
              </div>
              <div className="trade-rec-item">
                <label>Take Profit</label>
                <span className="trade-rec-value trade-rec-profit">${data.trade_recommendation.take_profit.toFixed(2)}</span>
              </div>
              <div className="trade-rec-item">
                <label>Stop Loss</label>
                <span className="trade-rec-value trade-rec-loss">${data.trade_recommendation.stop_loss.toFixed(2)}</span>
              </div>
              <div className="trade-rec-item">
                <label>Suggested Shares</label>
                <span className="trade-rec-value">{data.trade_recommendation.suggested_shares}</span>
              </div>
              <div className="trade-rec-item">
                <label>Position Value</label>
                <span className="trade-rec-value">${data.trade_recommendation.position_value.toFixed(2)}</span>
              </div>
              <div className="trade-rec-item">
                <label>Risk/Reward</label>
                <span className="trade-rec-value">1:{data.trade_recommendation.risk_reward_ratio}</span>
              </div>
              <div className="trade-rec-item potential-gain">
                <label>Potential Gain</label>
                <span className="trade-rec-value">+${data.trade_recommendation.potential_gain.toFixed(2)}</span>
              </div>
              <div className="trade-rec-item potential-loss">
                <label>Potential Loss</label>
                <span className="trade-rec-value">-${data.trade_recommendation.potential_loss.toFixed(2)}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  const handleClearChat = () => {
    const confirmed = window.confirm('Are you sure you want to clear all chat messages? This action cannot be undone.');
    if (confirmed) {
      setMessages([]);
      localStorage.removeItem('chatMessages');
    }
  };

  return (
    <div className="chat-container">
      <div className="chat-header">
        <h2>🤖 Chat with Trading Bot</h2>
        <div className="chat-header-controls">
          <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
            <span className="status-dot"></span>
            {isConnected ? 'Connected' : 'Disconnected'}
          </div>
          <button
            onClick={handleClearChat}
            className="clear-chat-button"
            title="Clear all chat messages"
          >
            🗑️ Clear Chat
          </button>
        </div>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="empty-chat">
            <div className="empty-chat-icon">💬</div>
            <p>Start a conversation!</p>
            <small>Try sending a stock ticker like "AAPL" or "TSLA"</small>
          </div>
        )}

        {messages.filter(msg => msg.content && msg.type).map((msg, index) => (
          <div key={index} className={getMessageClassName(msg.type)}>
            <div className="message-content">
              {msg.type === 'analysis' && msg.data ? (
                <>
                  <div className="message-title">{msg.content}</div>
                  {renderAnalysisData(msg.data)}
                </>
              ) : (
                formatMessageContent(msg.content)
              )}
            </div>
            <div className="message-timestamp">
              {msg.timestamp && !isNaN(msg.timestamp.getTime())
                ? msg.timestamp.toLocaleTimeString()
                : ''}
            </div>
          </div>
        ))}

        {isTyping && (
          <div className="message message-assistant">
            <div className="typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="chat-bottom-fixed">
        <div className="chat-disclaimer">
          ⚠️ For educational purposes only. Trading involves risk.
        </div>

        {!isConnected && (
          <div className="connection-warning">
            ⚠️ Disconnected from server. Refresh the page to reconnect.
          </div>
        )}

        <form className="chat-input-form" onSubmit={sendMessage}>
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Type a message... (e.g., AAPL, help, positions)"
            className="chat-input"
            disabled={!isConnected}
          />
          <button
            type="submit"
            className="chat-send-button"
            disabled={!isConnected || !inputValue.trim()}
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}

export default ChatTab;
