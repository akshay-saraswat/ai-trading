import React from 'react';

function MFAModal({ status, message, onClose }) {
  // Only show modal for these statuses
  const shouldShow = status === 'logging_in' || status === 'waiting_for_mfa';

  if (!shouldShow) {
    return null;
  }

  return (
    <div className="mfa-modal-overlay">
      <div className="mfa-modal">
        <div className="mfa-modal-content">
          {/* Spinner */}
          <div className="mfa-spinner-container">
            <div className="mfa-spinner"></div>
          </div>

          {/* Status Message */}
          <h2 className="mfa-title">
            {status === 'logging_in' ? '🔐 Logging In' : '📱 MFA Required'}
          </h2>

          <p className="mfa-message">
            {message || 'Please approve the login request on your Robinhood mobile app'}
          </p>

          {status === 'waiting_for_mfa' && (
            <div className="mfa-instructions">
              <p>✓ Open your Robinhood app</p>
              <p>✓ Approve the login notification</p>
              <p>✓ Wait for automatic completion</p>
            </div>
          )}

          {/* Subtle pulsing indicator */}
          <div className="mfa-pulse-indicator">
            <span className="pulse-dot"></span>
            <span className="pulse-text">Waiting for approval...</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default MFAModal;
