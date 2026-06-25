// ═══════════════════════════════════════════════════════════════════════════
// Yazaki Finance Policy Assistant — Chat Module
// Handles: message sending/receiving, typing effect, conversation history
// ═══════════════════════════════════════════════════════════════════════════

const ChatModule = {
    // ── DOM References ────────────────────────────────────────────────────
    messagesArea: null,
    messageInput: null,
    sendBtn: null,
    typingIndicator: null,
    welcomeMessage: null,

    // ── Initialization ────────────────────────────────────────────────────
    init() {
        this.messagesArea    = document.getElementById('messagesArea');
        this.messageInput    = document.getElementById('messageInput');
        this.sendBtn         = document.getElementById('sendBtn');
        this.typingIndicator = document.getElementById('typingIndicator');
        this.welcomeMessage  = document.getElementById('welcomeMessage');

        // Send on click
        this.sendBtn.addEventListener('click', () => this.sendMessage());

        // Send on Enter (Shift+Enter for new line)
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Auto-resize textarea as user types
        this.messageInput.addEventListener('input', () => this.autoResize());

        // Clear Chat
        const clearChatBtn = document.getElementById('clearChatBtn');
        if (clearChatBtn) {
            clearChatBtn.addEventListener('click', () => this.clearChat());
        }
    },

    // ══════════════════════════════════════════════════════════════════════
    //  CLEAR CHAT
    // ══════════════════════════════════════════════════════════════════════

    clearChat() {
        if (confirm("Are you sure you want to clear this conversation?")) {
            // Stop any active playing audio
            if (typeof VoiceModule !== 'undefined') {
                VoiceModule.stopAudio();
                VoiceModule.hideAudioControls();
            }
            
            // Clear message list in DOM
            if (this.messagesArea) {
                this.messagesArea.innerHTML = '';
            }

            // Clear conversation history
            KaizenApp.conversationHistory = [];

            // Restore the welcome screen display
            if (this.welcomeMessage) {
                this.welcomeMessage.style.display = 'flex';
            }

            showToast("Conversation cleared", "success");
        }
    },

    // ══════════════════════════════════════════════════════════════════════
    //  TEXTAREA AUTO-RESIZE
    // ══════════════════════════════════════════════════════════════════════

    autoResize() {
        this.messageInput.style.height = 'auto';
        this.messageInput.style.height =
            Math.min(this.messageInput.scrollHeight, 120) + 'px';
    },

    // ══════════════════════════════════════════════════════════════════════
    //  SEND MESSAGE
    // ══════════════════════════════════════════════════════════════════════

    async sendMessage(text = null) {
        // If recording is active, stop it
        if (typeof VoiceModule !== 'undefined' && VoiceModule.isRecording) {
            
            // Extract transcribed text early before stopping for mobile flow
            const transcribed = (VoiceModule.liveTranscript || VoiceModule.recognitionTranscript || '').trim();

            // Stop SpeechRecognition
            if (VoiceModule.recognition) {
                try { VoiceModule.recognition.stop(); } catch (e) {}
            }
            
            VoiceModule.isRecording = false;
            VoiceModule.voiceBtn.classList.remove('recording');
            KaizenApp.isRecording = false;
            
            // Hide the voice indicator overlay
            if (typeof VoiceModule.hideVoiceIndicator === 'function') {
                VoiceModule.hideVoiceIndicator();
            }

            // Desktop flow (MediaRecorder)
            if (VoiceModule.mediaRecorder) {
                // Do NOT set _manualStop=true so the onstop handler triggers processRecording()
                VoiceModule.mediaRecorder.stop();
                this.messageInput.value = '';
                this.messageInput.style.height = 'auto';
                this.autoResize();
                return; // Early return because processRecording will handle sending the audio
            } 
            
            // Mobile flow (SpeechRecognition only)
            if (transcribed) {
                text = transcribed; // Override text parameter and continue with normal send flow
            } else {
                this.messageInput.value = '';
                return; // Nothing to send
            }
        }

        const message = text || this.messageInput.value.trim();
        if (!message || KaizenApp.isProcessing) return;

        // Transition from welcome screen to chat
        if (this.welcomeMessage) {
            this.welcomeMessage.style.display = 'none';
        }

        // Always clear the input field after sending
        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';
        this.autoResize();

        // Render user message
        this.appendMessage('user', message);

        // Push to conversation history
        KaizenApp.conversationHistory.push({ role: 'user', content: message });

        // Enter processing state
        KaizenApp.isProcessing = true;
        this.showTypingIndicator();

        try {
            const response = await apiRequest('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: message,
                    conversation_history: KaizenApp.conversationHistory.slice(-10),
                }),
            });

            const data = await response.json();

            this.hideTypingIndicator();

            // Render AI response with typing animation
            await this.appendMessageWithTypingEffect(
                'assistant',
                data.response,
                data.sources
            );

            // Push to history
            KaizenApp.conversationHistory.push({
                role: 'assistant',
                content: data.response,
            });

            // Automatically play voice for text input
            if (typeof VoiceModule !== 'undefined') {
                VoiceModule.synthesizeAndPlay(data.response);
            }


        } catch (error) {
            this.hideTypingIndicator();
            showToast(error.message, 'error');
            this.appendMessage(
                'assistant',
                'Sorry, I encountered an error. Please try again.'
            );
        } finally {
            KaizenApp.isProcessing = false;
        }
    },

    // ══════════════════════════════════════════════════════════════════════
    //  RENDER MESSAGES
    // ══════════════════════════════════════════════════════════════════════

    /**
     * Immediately appends a fully-rendered message bubble.
     */
    appendMessage(role, content, sources = []) {
        const messageEl = document.createElement('div');
        messageEl.className = `message ${role}`;

        const timeStr = new Date().toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
        });

        const avatarHtml =
            role === 'assistant'
                ? '<img src="/static/assets/yazaki-avatar.png" alt="AI" class="message-avatar">'
                : `<div class="message-avatar user-avatar">
                       <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                           <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                           <circle cx="12" cy="7" r="4"></circle>
                       </svg>
                   </div>`;

        let sourcesHtml = ''; // Hidden as per requirement

        messageEl.innerHTML = `
            ${avatarHtml}
            <div class="message-content">
                <div class="message-bubble">${this.formatContent(content)}</div>
                ${sourcesHtml}
                <div class="message-time">${timeStr}</div>
            </div>
        `;

        this.messagesArea.appendChild(messageEl);
        this.scrollToBottom();
    },

    /**
     * Appends a message with a character-by-character typing animation.
     */
    async appendMessageWithTypingEffect(role, content, sources = []) {
        const messageEl = document.createElement('div');
        messageEl.className = `message ${role}`;

        const timeStr = new Date().toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
        });

        messageEl.innerHTML = `
            <img src="/static/assets/yazaki-avatar.png" alt="AI" class="message-avatar">
            <div class="message-content">
                <div class="message-bubble"><span class="typing-cursor"></span></div>
                <div class="message-time">${timeStr}</div>
            </div>
        `;

        this.messagesArea.appendChild(messageEl);

        const bubble = messageEl.querySelector('.message-bubble');

        // Extract plain text for the typing animation
        const formattedContent = this.formatContent(content);
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = formattedContent;
        const plainText = tempDiv.textContent;

        // Fast typing effect — 3 characters per tick, 10ms interval
        for (let i = 0; i < plainText.length; i += 3) {
            bubble.textContent = plainText.substring(0, i + 3);
            this.scrollToBottom();
            await new Promise((r) => setTimeout(r, 10));
        }

        // Replace with fully-formatted HTML content
        bubble.innerHTML = formattedContent;

        // Sources hidden as per requirement

        this.scrollToBottom();
    },

    // ══════════════════════════════════════════════════════════════════════
    //  CONTENT FORMATTING (lightweight Markdown)
    // ══════════════════════════════════════════════════════════════════════

    formatContent(content) {
        if (!content) return '';

        return content
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    },

    // ══════════════════════════════════════════════════════════════════════
    //  TYPING INDICATOR
    // ══════════════════════════════════════════════════════════════════════

    showTypingIndicator() {
        if (this.typingIndicator) {
            this.typingIndicator.classList.add('visible');
            this.scrollToBottom();
        }
    },

    hideTypingIndicator() {
        if (this.typingIndicator) {
            this.typingIndicator.classList.remove('visible');
        }
    },

    // ══════════════════════════════════════════════════════════════════════
    //  SCROLL MANAGEMENT
    // ══════════════════════════════════════════════════════════════════════

    scrollToBottom() {
        if (this.messagesArea) {
            this.messagesArea.scrollTop = this.messagesArea.scrollHeight;
        }
    },
};
