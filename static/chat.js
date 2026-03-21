/**
 * StreamAI Global Chat Module
 * Real-time chat powered by Supabase
 * 
 * Features:
 * - Real-time message updates via WebSocket
 * - Username-based authentication (localStorage)
 * - Rate limiting (1 message per second)
 * - Basic profanity filter
 * - Message pagination (100 messages)
 * - Auto-scroll to newest messages
 * - Join/leave notifications
 */

class ChatManager {
    constructor() {
        // Configuration
        this.RATE_LIMIT_MS = 1000; // 1 second between messages
        this.MESSAGE_LIMIT = 100;  // Load last 100 messages
        this.MAX_MESSAGE_LENGTH = 500;

        // State
        this.supabase = null;
        this.channel = null;
        this.username = null;
        this.userColor = null;
        this.lastMessageTime = 0;
        this.isConnected = false;
        this.initialized = false;
        this.pollInterval = null;
        this.messages = [];

        // DOM Elements (will be set on init)
        this.elements = {};

        // Profanity filter patterns
        this.profanityPatterns = this.buildProfanityPatterns();

        // User colors for visual distinction
        this.userColors = [
            '#3B82F6', '#8B5CF6', '#EC4899', '#F59E0B',
            '#10B981', '#06B6D4', '#6366F1', '#F43F5E',
            '#84CC16', '#14B8A6', '#A855F7', '#FB923C'
        ];
    }

    /**
     * Build profanity filter patterns
     */
    buildProfanityPatterns() {
        // Common profanity words - basic list, can be extended
        const words = [
            'fuck', 'shit', 'ass', 'bitch', 'damn', 'crap',
            'bastard', 'dick', 'piss', 'cock', 'pussy', 'cunt',
            'fag', 'slut', 'whore', 'nigger', 'retard'
        ];

        // Build regex patterns that catch common letter substitutions
        return words.map(word => {
            // Create pattern that matches common substitutions
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

    /**
     * Filter profanity from text
     */
    filterProfanity(text) {
        let filtered = text;
        this.profanityPatterns.forEach(pattern => {
            filtered = filtered.replace(pattern, match => '*'.repeat(match.length));
        });
        return filtered;
    }

    /**
     * Generate a consistent color for a username
     */
    getUserColor(username) {
        let hash = 0;
        for (let i = 0; i < username.length; i++) {
            hash = username.charCodeAt(i) + ((hash << 5) - hash);
        }
        return this.userColors[Math.abs(hash) % this.userColors.length];
    }

    /**
     * Initialize the chat system
     */
    async init() {
        console.log('🚀 Initializing Flimo Chat...');

        // ALWAYS update DOM elements ref (in case of SPA navigation)
        this.cacheElements();

        // Prevent duplicate logic initialization
        if (this.initialized) {
            console.log('Chat logic already initialized, refreshing view...');

            // Re-bind events to new elements
            this.bindEvents();

            // Re-render messages to new container
            this.renderMessages();

            // Check connection
            if (!this.isConnected && !this.pollInterval) {
                await this.connectToChat();
            }
            return;
        }

        // Check if Supabase is configured
        if (!window.isSupabaseConfigured || !window.isSupabaseConfigured()) {
            this.showConfigurationMessage();
            return;
        }

        // Initialize Supabase
        this.supabase = window.initSupabase();
        if (!this.supabase) {
            this.showError('Failed to initialize chat service');
            return;
        }

        // Mark as initialized
        this.initialized = true;

        // Check for existing username
        this.username = localStorage.getItem('streamai_chat_username');
        this.userColor = localStorage.getItem('streamai_chat_color');

        if (this.username) {
            // User already has a username, show chat
            this.showChatInterface();
            await this.connectToChat();
        } else {
            // Show username input
            this.showUsernameModal();
        }

        // Bind event listeners
        this.bindEvents();
    }

    /**
     * Cache DOM element references
     */
    cacheElements() {
        this.elements = {
            // Chat container
            chatContainer: document.getElementById('chat-container'),
            messagesContainer: document.getElementById('chat-messages'),
            inputArea: document.getElementById('chat-input-area'),
            messageInput: document.getElementById('chat-input'),
            sendButton: document.getElementById('chat-send-btn'),

            // Username modal
            usernameModal: document.getElementById('chat-username-modal'),
            usernameInput: document.getElementById('chat-username-input'),
            usernameSubmit: document.getElementById('chat-username-submit'),
            usernameError: document.getElementById('chat-username-error'),

            // Status elements
            connectionStatus: document.getElementById('chat-connection-status'),
            onlineCount: document.getElementById('chat-online-count'),

            // Rate limit warning
            rateLimitWarning: document.getElementById('chat-rate-limit-warning')
        };
    }

    /**
     * Bind event listeners
     */
    bindEvents() {
        // Send message on button click
        if (this.elements.sendButton) {
            this.elements.sendButton.addEventListener('click', () => this.sendMessage());
        }

        // Send message on Enter key
        if (this.elements.messageInput) {
            this.elements.messageInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }

        // Username submission
        if (this.elements.usernameSubmit) {
            this.elements.usernameSubmit.addEventListener('click', () => this.submitUsername());
        }

        if (this.elements.usernameInput) {
            this.elements.usernameInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.submitUsername();
                }
            });
        }
    }

    /**
     * Show username input modal
     */
    showUsernameModal() {
        if (this.elements.usernameModal) {
            this.elements.usernameModal.classList.remove('hidden');
        }
        if (this.elements.inputArea) {
            this.elements.inputArea.classList.add('hidden');
        }
        // Hide placeholder message
        const placeholder = this.elements.messagesContainer?.querySelector('.chat-placeholder');
        if (placeholder) {
            placeholder.textContent = 'Enter a username to join the chat!';
        }
    }

    /**
     * Submit username and join chat
     */
    async submitUsername() {
        const input = this.elements.usernameInput;
        const error = this.elements.usernameError;

        if (!input) return;

        const username = input.value.trim();

        // Validate username
        if (!username) {
            this.showUsernameError('Please enter a username');
            return;
        }

        if (username.length < 2) {
            this.showUsernameError('Username must be at least 2 characters');
            return;
        }

        if (username.length > 20) {
            this.showUsernameError('Username must be 20 characters or less');
            return;
        }

        if (!/^[a-zA-Z0-9_\- ]+$/.test(username)) {
            this.showUsernameError('Username can only contain letters, numbers, spaces, - and _');
            return;
        }

        // Filter profanity from username
        const filteredUsername = this.filterProfanity(username);
        if (filteredUsername !== username) {
            this.showUsernameError('Please choose an appropriate username');
            return;
        }

        // Save username
        this.username = username;
        this.userColor = this.getUserColor(username);
        localStorage.setItem('streamai_chat_username', username);
        localStorage.setItem('streamai_chat_color', this.userColor);

        // Hide modal and show chat
        if (this.elements.usernameModal) {
            this.elements.usernameModal.classList.add('hidden');
        }

        this.showChatInterface();
        await this.connectToChat();

        // Send join notification
        this.addSystemMessage(`${username} joined the chat`);
    }

    /**
     * Show username error message
     */
    showUsernameError(message) {
        if (this.elements.usernameError) {
            this.elements.usernameError.textContent = message;
            this.elements.usernameError.classList.remove('hidden');
        }
    }

    /**
     * Show chat interface (input area)
     */
    showChatInterface() {
        if (this.elements.inputArea) {
            this.elements.inputArea.classList.remove('hidden');
        }

        // Remove placeholder
        const placeholder = this.elements.messagesContainer?.querySelector('.chat-placeholder');
        if (placeholder) {
            placeholder.remove();
        }

        // Update connection status
        this.updateConnectionStatus('connecting');
    }

    /**
     * Connect to chat room and load messages
     */
    async connectToChat() {
        try {
            // Load existing messages
            await this.loadMessages();

            // Subscribe to new messages
            this.subscribeToMessages();

            this.isConnected = true;
            this.updateConnectionStatus('connected');

            console.log('✅ Connected to chat room');
        } catch (error) {
            console.error('❌ Failed to connect to chat:', error);
            this.showError('Failed to connect to chat. Please try again.');
            this.updateConnectionStatus('error');
        }
    }

    /**
     * Load existing messages from database
     */
    async loadMessages() {
        const { data, error } = await this.supabase
            .from('chat_messages')
            .select('*')
            .order('created_at', { ascending: false })
            .limit(this.MESSAGE_LIMIT);

        if (error) {
            console.error('Error loading messages:', error);
            throw error;
        }

        // Reverse to show oldest first
        this.messages = (data || []).reverse();

        // Render messages
        this.renderMessages();
    }

    /**
     * Subscribe to real-time message updates
     */
    subscribeToMessages() {
        this.channel = this.supabase
            .channel('chat-room')
            .on(
                'postgres_changes',
                {
                    event: 'INSERT',
                    schema: 'public',
                    table: 'chat_messages'
                },
                (payload) => {
                    this.handleNewMessage(payload.new);
                }
            )
            .subscribe((status) => {
                console.log('Subscription status:', status);
                if (status === 'SUBSCRIBED') {
                    this.updateConnectionStatus('connected');
                    // Stop polling if realtime works
                    if (this.pollInterval) {
                        clearInterval(this.pollInterval);
                        this.pollInterval = null;
                    }
                } else if (status === 'CLOSED' || status === 'CHANNEL_ERROR') {
                    this.updateConnectionStatus('connected'); // Still show connected since we'll poll
                    // Start polling as fallback
                    this.startPolling();
                }
            });
    }

    /**
     * Start polling for new messages (fallback when realtime fails)
     */
    startPolling() {
        if (this.pollInterval) return; // Already polling

        console.log('Starting message polling fallback...');
        this.pollInterval = setInterval(async () => {
            await this.pollNewMessages();
        }, 3000); // Poll every 3 seconds
    }

    /**
     * Poll for new messages
     */
    async pollNewMessages() {
        try {
            const lastMessage = this.messages[this.messages.length - 1];
            const lastTime = lastMessage ? lastMessage.created_at : new Date(0).toISOString();

            const { data, error } = await this.supabase
                .from('chat_messages')
                .select('*')
                .gt('created_at', lastTime)
                .order('created_at', { ascending: true })
                .limit(50);

            if (error) {
                console.error('Poll error:', error);
                return;
            }

            if (data && data.length > 0) {
                data.forEach(msg => this.handleNewMessage(msg));
            }
        } catch (error) {
            console.error('Poll error:', error);
        }
    }

    /**
     * Handle incoming new message
     */
    handleNewMessage(message) {
        // Check for duplicate (message already exists)
        if (this.messages.some(m => m.id === message.id)) {
            return; // Already have this message
        }

        // Add to messages array
        this.messages.push(message);

        // Keep only last MESSAGE_LIMIT messages in memory
        if (this.messages.length > this.MESSAGE_LIMIT) {
            this.messages.shift();
            // Re-render all messages when removing old ones
            this.renderMessages();
            return;
        }

        // Render the new message
        this.appendMessage(message);

        // Auto-scroll to bottom
        this.scrollToBottom();
    }

    /**
     * Render all messages
     */
    renderMessages() {
        if (!this.elements.messagesContainer) return;

        // Clear existing messages (except system messages)
        this.elements.messagesContainer.innerHTML = '';

        // Render each message
        this.messages.forEach(msg => this.appendMessage(msg));

        // Scroll to bottom
        this.scrollToBottom();
    }

    /**
     * Append a single message to the chat
     */
    appendMessage(message) {
        if (!this.elements.messagesContainer) return;

        const messageEl = document.createElement('div');
        messageEl.className = 'chat-message';
        messageEl.dataset.messageId = message.id;

        const isOwnMessage = message.username === this.username;
        if (isOwnMessage) {
            messageEl.classList.add('own-message');
        }

        const time = this.formatTime(message.created_at);
        const color = message.user_color || this.getUserColor(message.username);

        messageEl.innerHTML = `
            <div class="message-header">
                <span class="message-username" style="color: ${color}">${this.escapeHtml(message.username)}</span>
                <span class="message-time">${time}</span>
            </div>
            <div class="message-content">${this.escapeHtml(message.message)}</div>
        `;

        this.elements.messagesContainer.appendChild(messageEl);
    }

    /**
     * Add a system message (join/leave notifications)
     */
    addSystemMessage(text) {
        if (!this.elements.messagesContainer) return;

        const messageEl = document.createElement('div');
        messageEl.className = 'chat-message system-message';
        messageEl.innerHTML = `<div class="message-content">${this.escapeHtml(text)}</div>`;

        this.elements.messagesContainer.appendChild(messageEl);
        this.scrollToBottom();
    }

    /**
     * Send a message
     */
    async sendMessage() {
        const input = this.elements.messageInput;
        if (!input || !this.username) return;

        let message = input.value.trim();

        // Validate message
        if (!message) {
            return; // Empty message, ignore
        }

        if (message.length > this.MAX_MESSAGE_LENGTH) {
            message = message.substring(0, this.MAX_MESSAGE_LENGTH);
        }

        // Check rate limit
        if (!this.checkRateLimit()) {
            return;
        }

        // Filter profanity
        message = this.filterProfanity(message);

        // Clear input
        input.value = '';

        // Send to Supabase
        try {
            const { error } = await this.supabase
                .from('chat_messages')
                .insert({
                    username: this.username,
                    message: message,
                    user_color: this.userColor
                });

            if (error) {
                console.error('Error sending message:', error);
                this.showError('Failed to send message');
                input.value = message; // Restore message
            }
        } catch (error) {
            console.error('Error sending message:', error);
            this.showError('Failed to send message');
            input.value = message; // Restore message
        }
    }

    /**
     * Check rate limit
     */
    checkRateLimit() {
        const now = Date.now();
        const timeSinceLastMessage = now - this.lastMessageTime;

        if (timeSinceLastMessage < this.RATE_LIMIT_MS) {
            this.showRateLimitWarning();
            return false;
        }

        this.lastMessageTime = now;
        return true;
    }

    /**
     * Show rate limit warning
     */
    showRateLimitWarning() {
        if (this.elements.rateLimitWarning) {
            this.elements.rateLimitWarning.classList.remove('hidden');
            setTimeout(() => {
                this.elements.rateLimitWarning.classList.add('hidden');
            }, 2000);
        } else {
            // Fallback: flash the input
            if (this.elements.messageInput) {
                this.elements.messageInput.classList.add('rate-limited');
                setTimeout(() => {
                    this.elements.messageInput.classList.remove('rate-limited');
                }, 500);
            }
        }
    }

    /**
     * Update connection status indicator
     */
    updateConnectionStatus(status) {
        if (!this.elements.connectionStatus) return;

        this.elements.connectionStatus.className = `connection-status ${status}`;

        const statusText = {
            'connecting': 'Connecting...',
            'connected': 'Connected',
            'disconnected': 'Disconnected',
            'error': 'Error'
        };

        this.elements.connectionStatus.textContent = statusText[status] || status;
    }

    /**
     * Scroll to bottom of messages
     */
    scrollToBottom() {
        if (this.elements.messagesContainer) {
            this.elements.messagesContainer.scrollTop = this.elements.messagesContainer.scrollHeight;
        }
    }

    /**
     * Format timestamp for display
     */
    formatTime(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();

        // Today: show time only
        if (date.toDateString() === now.toDateString()) {
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }

        // This week: show day and time
        const daysDiff = Math.floor((now - date) / (1000 * 60 * 60 * 24));
        if (daysDiff < 7) {
            return date.toLocaleDateString([], { weekday: 'short' }) + ' ' +
                date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }

        // Older: show date and time
        return date.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' +
            date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Show error message
     */
    showError(message) {
        console.error(message);
        // Could show a toast notification here
    }

    /**
     * Show configuration message when Supabase is not set up
     */
    showConfigurationMessage() {
        if (!this.elements.messagesContainer) return;

        this.elements.messagesContainer.innerHTML = `
            <div class="chat-config-message">
                <div class="config-icon">⚙️</div>
                <h4>Chat Setup Required</h4>
                <p>To enable real-time chat, please configure Supabase:</p>
                <ol>
                    <li>Create a free project at <a href="https://supabase.com" target="_blank">supabase.com</a></li>
                    <li>Run the database schema (see CHAT_SETUP.md)</li>
                    <li>Update <code>supabase-config.js</code> with your credentials</li>
                </ol>
            </div>
        `;

        if (this.elements.inputArea) {
            this.elements.inputArea.classList.add('hidden');
        }
    }

    /**
     * Disconnect from chat
     */
    disconnect() {
        if (this.channel) {
            this.supabase.removeChannel(this.channel);
            this.channel = null;
        }
        this.isConnected = false;
        this.updateConnectionStatus('disconnected');
    }

    /**
     * Change username
     */
    changeUsername() {
        localStorage.removeItem('streamai_chat_username');
        localStorage.removeItem('streamai_chat_color');
        this.username = null;
        this.userColor = null;
        this.showUsernameModal();
    }
}

// Create global instance only if it doesn't exist
if (!window.chatManager) {
    window.chatManager = new ChatManager();
}

// Initialize when DOM is ready and on community page
document.addEventListener('DOMContentLoaded', () => {
    // Check if we're on the community page or if chat container exists
    const chatContainer = document.getElementById('chat-container');
    if (chatContainer && window.chatManager && !window.chatManager.initialized) {
        // Wait a bit for Supabase script to load
        setTimeout(() => {
            window.chatManager.init();
        }, 100);
    }
});

// Also initialize when navigating to community page (SPA support)
window.initChat = function () {
    if (window.chatManager && !window.chatManager.initialized) {
        window.chatManager.init();
    }
};
