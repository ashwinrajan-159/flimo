/**
 * Flimo Chat Module
 * Real-time chat powered by FastAPI backend + polling
 * 
 * Features:
 * - Backend-persisted messages (SQLite)
 * - Polling for new messages (3s interval)
 * - Username from auth (email-based)
 * - Rate limiting (1 message per second)
 * - Basic profanity filter
 * - Auto-scroll to newest messages
 */

class ChatManager {
    constructor() {
        // Configuration
        this.API_BASE = 'http://127.0.0.1:8000';
        this.RATE_LIMIT_MS = 1000;
        this.MAX_MESSAGE_LENGTH = 500;
        this.POLL_INTERVAL_MS = 3000;

        // State
        this.lastMessageTime = 0;
        this.isConnected = false;
        this.initialized = false;
        this.pollInterval = null;
        this.messages = [];

        // DOM Elements
        this.elements = {};

        // Profanity filter
        this.profanityPatterns = this.buildProfanityPatterns();

        // User colors for visual distinction
        this.userColors = [
            '#3B82F6', '#8B5CF6', '#EC4899', '#F59E0B',
            '#10B981', '#06B6D4', '#6366F1', '#F43F5E',
            '#84CC16', '#14B8A6', '#A855F7', '#FB923C'
        ];
    }

    buildProfanityPatterns() {
        const words = [
            'fuck', 'shit', 'ass', 'bitch', 'damn', 'crap',
            'bastard', 'dick', 'piss', 'cock', 'pussy', 'cunt',
            'fag', 'slut', 'whore', 'nigger', 'retard'
        ];
        return words.map(word => {
            const pattern = word
                .replace(/a/gi, '[a@4]')
                .replace(/e/gi, '[e3]')
                .replace(/i/gi, '[i1!]')
                .replace(/o/gi, '[o0]')
                .replace(/s/gi, '[s$5]')
                .replace(/t/gi, '[t7]');
            return new RegExp(`\\b${pattern}\\b`, 'gi');
        });
    }

    filterProfanity(text) {
        let filtered = text;
        this.profanityPatterns.forEach(pattern => {
            filtered = filtered.replace(pattern, match => '*'.repeat(match.length));
        });
        return filtered;
    }

    getUserColor(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            hash = str.charCodeAt(i) + ((hash << 5) - hash);
        }
        return this.userColors[Math.abs(hash) % this.userColors.length];
    }

    /**
     * Initialize the chat system
     */
    async init() {
        console.log('Initializing Flimo Chat (Backend Mode)...');

        // ALWAYS refresh DOM element refs (SPA navigation)
        this.cacheElements();

        if (this.initialized) {
            // Re-bind events and re-render
            this.bindEvents();
            this.renderMessages();
            if (!this.pollInterval) {
                await this.connectToChat();
            }
            return;
        }

        this.initialized = true;

        // Check if user is logged in
        if (this.isUserLoggedIn()) {
            this.showChatInterface();
            await this.connectToChat();
        } else {
            this.showLoginPrompt();
        }

        this.bindEvents();
    }

    isUserLoggedIn() {
        return !!localStorage.getItem('flimo_jwt_token') || !!localStorage.getItem('streamai_user_email');
    }

    getAuthHeaders() {
        const headers = { 'Content-Type': 'application/json' };
        const token = localStorage.getItem('flimo_jwt_token') || localStorage.getItem('streamai_jwt_token');
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        // Fallback to email header
        const email = localStorage.getItem('flimo_user_email') || localStorage.getItem('streamai_user_email');
        if (email) {
            headers['x-user-email'] = email;
        }
        return headers;
    }

    getUserDisplayName() {
        return localStorage.getItem('flimo_user_name') ||
               localStorage.getItem('streamai_user_email')?.split('@')[0] ||
               'Anonymous';
    }

    cacheElements() {
        this.elements = {
            chatContainer: document.getElementById('chat-container'),
            messagesContainer: document.getElementById('chat-messages'),
            inputArea: document.getElementById('chat-input-area'),
            messageInput: document.getElementById('chat-input'),
            sendButton: document.getElementById('chat-send-btn'),
            connectionStatus: document.getElementById('chat-connection-status'),
            rateLimitWarning: document.getElementById('chat-rate-limit-warning'),
            usernameModal: document.getElementById('chat-username-modal'),
        };
    }

    bindEvents() {
        if (this.elements.sendButton) {
            // Remove old listeners by cloning
            const newBtn = this.elements.sendButton.cloneNode(true);
            this.elements.sendButton.parentNode?.replaceChild(newBtn, this.elements.sendButton);
            this.elements.sendButton = newBtn;
            this.elements.sendButton.addEventListener('click', () => this.sendMessage());
        }

        if (this.elements.messageInput) {
            const newInput = this.elements.messageInput.cloneNode(true);
            this.elements.messageInput.parentNode?.replaceChild(newInput, this.elements.messageInput);
            this.elements.messageInput = newInput;
            this.elements.messageInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }
    }

    showLoginPrompt() {
        if (this.elements.inputArea) {
            this.elements.inputArea.classList.add('hidden');
        }
        if (this.elements.messagesContainer) {
            this.elements.messagesContainer.innerHTML = `
                <div class="chat-config-message">
                    <div class="config-icon">💬</div>
                    <h4>Join the Chat</h4>
                    <p>Sign in to start chatting with the community!</p>
                </div>
            `;
        }
        if (this.elements.usernameModal) {
            this.elements.usernameModal.classList.add('hidden');
        }
        this.updateConnectionStatus('disconnected');
    }

    showChatInterface() {
        if (this.elements.inputArea) {
            this.elements.inputArea.classList.remove('hidden');
        }
        if (this.elements.usernameModal) {
            this.elements.usernameModal.classList.add('hidden');
        }
        const placeholder = this.elements.messagesContainer?.querySelector('.chat-config-message');
        if (placeholder) placeholder.remove();

        this.updateConnectionStatus('connecting');
    }

    async connectToChat() {
        try {
            await this.loadMessages();
            this.startPolling();
            this.isConnected = true;
            this.updateConnectionStatus('connected');
        } catch (error) {
            console.error('Failed to connect to chat:', error);
            this.updateConnectionStatus('error');
            // Show messages container even on error
            if (this.elements.messagesContainer) {
                this.elements.messagesContainer.innerHTML =
                    '<p class="text-muted chat-placeholder">Failed to load chat. Messages will appear when the server is ready.</p>';
            }
        }
    }

    async loadMessages() {
        const res = await fetch(`${this.API_BASE}/chat`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        this.messages = await res.json();
        this.renderMessages();
    }

    startPolling() {
        if (this.pollInterval) return;

        this.pollInterval = setInterval(async () => {
            try {
                const res = await fetch(`${this.API_BASE}/chat`);
                if (!res.ok) return;

                const newMessages = await res.json();

                // Check if there are truly new messages
                if (newMessages.length !== this.messages.length) {
                    this.messages = newMessages;
                    this.renderMessages();
                }
            } catch (e) {
                // Silently fail, will retry
            }
        }, this.POLL_INTERVAL_MS);
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    renderMessages() {
        if (!this.elements.messagesContainer) return;

        if (this.messages.length === 0) {
            this.elements.messagesContainer.innerHTML =
                '<p class="text-muted chat-placeholder">No messages yet. Start the conversation!</p>';
            return;
        }

        const currentUserId = localStorage.getItem('flimo_user_id');

        this.elements.messagesContainer.innerHTML = this.messages.map(msg => {
            const isOwn = msg.user_id === currentUserId;
            const time = this.formatTime(msg.created_at);
            const displayName = msg.display_name || 'Anonymous';
            const color = msg.avatar_color || this.getUserColor(displayName);

            return `
                <div class="chat-message ${isOwn ? 'own-message' : ''}">
                    <div class="message-header">
                        <span class="message-username" style="color: ${color}">${this.escapeHtml(displayName)}</span>
                        <span class="message-time">${time}</span>
                    </div>
                    <div class="message-content">${this.escapeHtml(msg.message)}</div>
                </div>
            `;
        }).join('');

        this.scrollToBottom();
    }

    async sendMessage() {
        const input = this.elements.messageInput;
        if (!input) return;

        let message = input.value.trim();
        if (!message) return;

        if (message.length > this.MAX_MESSAGE_LENGTH) {
            message = message.substring(0, this.MAX_MESSAGE_LENGTH);
        }

        // Rate limit
        const now = Date.now();
        if (now - this.lastMessageTime < this.RATE_LIMIT_MS) {
            this.showRateLimitWarning();
            return;
        }
        this.lastMessageTime = now;

        // Filter
        message = this.filterProfanity(message);

        // Clear input
        input.value = '';

        try {
            const res = await fetch(`${this.API_BASE}/chat`, {
                method: 'POST',
                headers: this.getAuthHeaders(),
                body: JSON.stringify({ message })
            });

            if (!res.ok) {
                if (res.status === 401 || res.status === 403) {
                    alert('Please sign in to send messages.');
                    input.value = message;
                    return;
                }
                throw new Error(`HTTP ${res.status}`);
            }

            // Immediately load new messages
            await this.loadMessages();
        } catch (error) {
            console.error('Error sending message:', error);
            input.value = message; // Restore on failure
        }
    }

    showRateLimitWarning() {
        if (this.elements.rateLimitWarning) {
            this.elements.rateLimitWarning.classList.remove('hidden');
            setTimeout(() => {
                this.elements.rateLimitWarning.classList.add('hidden');
            }, 2000);
        }
    }

    updateConnectionStatus(status) {
        if (!this.elements.connectionStatus) return;

        this.elements.connectionStatus.className = `connection-status ${status}`;
        const statusText = {
            'connecting': 'Connecting...',
            'connected': 'Connected',
            'disconnected': 'Offline',
            'error': 'Error'
        };
        this.elements.connectionStatus.textContent = statusText[status] || status;
    }

    scrollToBottom() {
        if (this.elements.messagesContainer) {
            this.elements.messagesContainer.scrollTop = this.elements.messagesContainer.scrollHeight;
        }
    }

    formatTime(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();

        if (date.toDateString() === now.toDateString()) {
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }

        const daysDiff = Math.floor((now - date) / (1000 * 60 * 60 * 24));
        if (daysDiff < 7) {
            return date.toLocaleDateString([], { weekday: 'short' }) + ' ' +
                date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }

        return date.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' +
            date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    disconnect() {
        this.stopPolling();
        this.isConnected = false;
        this.updateConnectionStatus('disconnected');
    }
}

// Create global instance
if (!window.chatManager) {
    window.chatManager = new ChatManager();
}

// SPA support
window.initChat = function () {
    if (window.chatManager) {
        window.chatManager.init();
    }
};
