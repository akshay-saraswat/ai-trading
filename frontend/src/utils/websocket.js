// Global WebSocket manager - maintains connection across component unmounts
class WebSocketManager {
  constructor() {
    this.ws = null;
    this.messageCallbacks = new Set();
    this.statusCallbacks = new Set();
    this.isConnected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.messageQueue = []; // Queue messages when no subscribers
  }

  connect() {
    // Don't create a new connection if we already have one
    if (this.ws && this.ws.readyState !== WebSocket.CLOSED && this.ws.readyState !== WebSocket.CLOSING) {
      console.log('WebSocket already connected or connecting');
      this.notifyStatusCallbacks(this.ws.readyState === WebSocket.OPEN);
      return;
    }

    // Check if running in development (React dev server on port 3000)
    const isDevelopment = window.location.port === '3000';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = isDevelopment ? 'localhost:8000' : window.location.host;
    const wsUrl = `${protocol}//${host}/ws`;

    console.log('Connecting to WebSocket:', wsUrl);
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.isConnected = true;
      this.reconnectAttempts = 0;
      this.notifyStatusCallbacks(true);
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Validate message data
        if (!data.type || !data.message) {
          console.warn('Received invalid message data:', data);
          return;
        }

        const message = {
          type: data.type,
          content: data.message,
          timestamp: data.timestamp ? new Date(data.timestamp) : new Date(),
          data: data.data
        };

        // Notify all registered callbacks
        this.notifyMessageCallbacks(message);
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      this.isConnected = false;
      this.notifyStatusCallbacks(false);
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      this.isConnected = false;
      this.notifyStatusCallbacks(false);

      // Attempt to reconnect
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
        setTimeout(() => this.connect(), 2000);
      }
    };
  }

  send(message) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
      return true;
    }
    console.error('WebSocket not connected');
    return false;
  }

  // Register a callback for incoming messages
  onMessage(callback) {
    this.messageCallbacks.add(callback);

    // Deliver any queued messages
    if (this.messageQueue.length > 0) {
      console.log(`Delivering ${this.messageQueue.length} queued messages`);
      this.messageQueue.forEach(message => {
        try {
          callback(message);
        } catch (error) {
          console.error('Error delivering queued message:', error);
        }
      });
      this.messageQueue = []; // Clear the queue
    }

    // Return unsubscribe function
    return () => {
      this.messageCallbacks.delete(callback);
    };
  }

  // Register a callback for connection status changes
  onStatusChange(callback) {
    this.statusCallbacks.add(callback);

    // Immediately notify of current status
    callback(this.isConnected);

    // Return unsubscribe function
    return () => {
      this.statusCallbacks.delete(callback);
    };
  }

  notifyMessageCallbacks(message) {
    // If there are subscribers, deliver the message
    if (this.messageCallbacks.size > 0) {
      this.messageCallbacks.forEach(callback => {
        try {
          callback(message);
        } catch (error) {
          console.error('Error in message callback:', error);
        }
      });
    } else {
      // No subscribers, queue the message
      console.log('No message subscribers, queuing message');
      this.messageQueue.push(message);
    }
  }

  notifyStatusCallbacks(isConnected) {
    this.statusCallbacks.forEach(callback => {
      try {
        callback(isConnected);
      } catch (error) {
        console.error('Error in status callback:', error);
      }
    });
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

// Create a singleton instance
const wsManager = new WebSocketManager();

export default wsManager;
