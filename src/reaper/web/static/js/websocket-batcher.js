/**
 * WebSocket Batching Handler for Cloud-Reaper
 * Handles batched WebSocket messages from the server
 */

class WebSocketBatchHandler {
    constructor(socket) {
        this.socket = socket;
        this.messageQueues = {};
        this.processingIntervals = {};
        this.setupBatchListeners();
    }
    
    setupBatchListeners() {
        // Listen for batched metric updates
        this.socket.on('metric_update_batch', (data) => {
            this.handleBatchedMessage('metric_update', data);
        });
        
        // Listen for batched log messages
        this.socket.on('new_log_batch', (data) => {
            this.handleBatchedMessage('new_log', data);
        });
        
        // Generic batch handler for any event
        this.socket.onAny((eventName, data) => {
            if (eventName.endsWith('_batch')) {
                const baseEvent = eventName.replace('_batch', '');
                this.handleBatchedMessage(baseEvent, data);
            }
        });
    }
    
    handleBatchedMessage(baseEvent, data) {
        const { messages, count } = data;
        
        if (!messages || !Array.isArray(messages)) {
            console.warn(`[WebSocket Batch Handler] Invalid batch data for ${baseEvent}`);
            return;
        }
        
        console.log(`[WebSocket Batch Handler] Processing ${count} batched messages for ${baseEvent}`);
        
        // Process each message in the batch
        messages.forEach((message) => {
            // Trigger any local socket listeners without sending back to server
            if (typeof this.socket.listeners === 'function') {
                const listeners = this.socket.listeners(baseEvent);
                if (listeners && listeners.length > 0) {
                    listeners.forEach(fn => {
                        try { fn(message); } catch (e) { console.error(`[WebSocket Batch Handler] Listener error for ${baseEvent}:`, e); }
                    });
                }
            }
            
            // Also trigger document event handlers
            const customEvent = new CustomEvent(baseEvent, { detail: message });
            document.dispatchEvent(customEvent);
        });
        
        // Emit batch completion event
        const batchCompleteEvent = new CustomEvent(`${baseEvent}_batch_complete`, {
            detail: { count, baseEvent }
        });
        document.dispatchEvent(batchCompleteEvent);
    }
    
    // Method to queue messages for client-side batching (optional)
    queueMessage(event, data, options = {}) {
        const { maxBatchSize = 50, batchInterval = 150 } = options;
        
        if (!this.messageQueues[event]) {
            this.messageQueues[event] = [];
        }
        
        this.messageQueues[event].push(data);
        
        // Send immediately if batch size exceeded
        if (this.messageQueues[event].length >= maxBatchSize) {
            this.flushQueue(event);
        } else {
            // Set timer to flush after interval
            if (!this.processingIntervals[event]) {
                this.processingIntervals[event] = setTimeout(() => {
                    this.flushQueue(event);
                }, batchInterval);
            }
        }
    }
    
    flushQueue(event) {
        if (this.processingIntervals[event]) {
            clearTimeout(this.processingIntervals[event]);
            delete this.processingIntervals[event];
        }
        
        if (this.messageQueues[event] && this.messageQueues[event].length > 0) {
            const messages = this.messageQueues[event];
            this.messageQueues[event] = [];
            
            this.socket.emit(`${event}_batch`, {
                messages,
                count: messages.length
            });
        }
    }
    
    // Flush all pending queues
    flushAll() {
        Object.keys(this.messageQueues).forEach(event => {
            this.flushQueue(event);
        });
    }
}

// Initialize batch handler when Socket.IO connects
let batchHandler = null;

document.addEventListener('DOMContentLoaded', () => {
    if (typeof io !== 'undefined') {
        const socket = io();
        
        socket.on('connect', () => {
            console.log('[WebSocket Batch Handler] Connected to server');
            batchHandler = new WebSocketBatchHandler(socket);
        });
        
        socket.on('disconnect', () => {
            console.log('[WebSocket Batch Handler] Disconnected from server');
            if (batchHandler) {
                batchHandler.flushAll();
            }
        });
    }
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { WebSocketBatchHandler };
}
