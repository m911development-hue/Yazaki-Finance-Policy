// ═══════════════════════════════════════════════════════════════════════════
// Yazaki Finance Policy Assistant — Voice Module
// Handles: microphone recording, STT, TTS, audio playback
// ═══════════════════════════════════════════════════════════════════════════

const VoiceModule = {
    // ── DOM References ────────────────────────────────────────────────────
    voiceBtn: null,
    audioControls: null,

    // ── State ─────────────────────────────────────────────────────────────
    mediaRecorder: null,
    audioChunks: [],
    isRecording: false,
    currentAudio: null,
    lastAudioUrl: null,
    recognition: null,
    recognitionTranscript: '',
    liveTranscript: '',
    currentUtterance: null,
    lastSynthesizedText: '',

    // ── Initialization ────────────────────────────────────────────────────
    init() {
        this.voiceBtn      = document.getElementById('voiceBtn');
        this.audioControls = document.getElementById('audioControls');

        // Initialize SpeechRecognition if available
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            this.recognition = new SpeechRecognition();
            this.recognition.continuous = true;
            this.recognition.interimResults = true;
            this.recognition.lang = 'en-IN';

            this.recognition.onresult = (event) => {
                let interimTranscript = '';
                let finalTranscript = '';
                for (let i = event.resultIndex; i < event.results.length; ++i) {
                    if (event.results[i].isFinal) {
                        finalTranscript += event.results[i][0].transcript;
                    } else {
                        interimTranscript += event.results[i][0].transcript;
                    }
                }
                
                const accumulatedText = (this.recognitionTranscript + ' ' + finalTranscript + ' ' + interimTranscript).trim();
                this.liveTranscript = accumulatedText;

                // Update live transcript in the status text
                const statusText = document.querySelector('.voice-status-text');
                if (statusText) {
                    statusText.textContent = accumulatedText ? `Listening: "${accumulatedText}"` : 'Listening...';
                }
                
                // Update the input textarea in real-time ONLY while recording
                if (this.isRecording) {
                    const inputField = document.getElementById('messageInput');
                    if (inputField) {
                        inputField.value = accumulatedText;
                        if (typeof ChatModule !== 'undefined' && ChatModule.autoResize) {
                            ChatModule.autoResize();
                        }
                    }
                }

                if (finalTranscript) {
                    this.recognitionTranscript += ' ' + finalTranscript;
                }
            };

            this.recognition.onerror = (event) => {
                console.warn('Speech recognition error:', event.error);
            };
        }

        // Toggle recording on mic button click
        this.voiceBtn.addEventListener('click', () => this.toggleRecording());

        // Stop listening button inside voice overlay
        const stopListeningBtn = document.getElementById('stopListeningBtn');
        if (stopListeningBtn) {
            stopListeningBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.stopRecording();
            });
        }

        // Audio control buttons
        const stopBtn   = document.getElementById('audioStopBtn');
        const replayBtn = document.getElementById('audioReplayBtn');

        if (stopBtn)   stopBtn.addEventListener('click', () => this.stopAudio());
        if (replayBtn) replayBtn.addEventListener('click', () => this.replayAudio());
    },

    // ══════════════════════════════════════════════════════════════════════
    //  RECORDING
    // ══════════════════════════════════════════════════════════════════════

    async toggleRecording() {
        if (this.isRecording) {
            this.stopRecording();
        } else {
            await this.startRecording();
        }
    },

    async startRecording() {
        try {
            const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
            
            // On mobile, prefer native SpeechRecognition and skip MediaRecorder 
            // to avoid microphone lock conflicts (which causes the Google STT error).
            if (isMobile && this.recognition) {
                this.recognitionTranscript = '';
                this.liveTranscript = '';
                const inputField = document.getElementById('messageInput');
                if (inputField) inputField.value = '';
                
                this.recognition.start();
                this.isRecording = true;
                this.voiceBtn.classList.add('recording');
                KaizenApp.isRecording = true;
                
                const voiceInd = document.getElementById('voiceIndicator');
                if (voiceInd) {
                    voiceInd.classList.remove('processing');
                    voiceInd.classList.add('active');
                    const statusText = voiceInd.querySelector('.voice-status-text');
                    if (statusText) statusText.textContent = 'Listening...';
                }
                showToast('Listening...', 'info', 2000);
                return;
            }

            // Desktop flow: Use MediaRecorder + SpeechRecognition
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 44100 }
            });

            // Determine a supported MIME type dynamically (fixes iOS/Safari issues)
            const types = [
                'audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/m4a', 'audio/aac', 'audio/ogg'
            ];
            let mimeType = '';
            for (let t of types) {
                if (MediaRecorder.isTypeSupported(t)) {
                    mimeType = t;
                    break;
                }
            }
            
            const options = mimeType ? { mimeType } : {};
            this.mediaRecorder = new MediaRecorder(stream, options);
            this.audioChunks = [];

            this.mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) this.audioChunks.push(e.data);
            };

            this.mediaRecorder.onstop = () => {
                stream.getTracks().forEach((t) => t.stop());
                if (this._manualStop) {
                    this._manualStop = false;
                } else {
                    this.processRecording();
                }
            };

            if (this.recognition) {
                this.recognitionTranscript = '';
                this.liveTranscript = '';
                const inputField = document.getElementById('messageInput');
                if (inputField) inputField.value = '';
                try { this.recognition.start(); } catch (e) { console.warn('SpeechRecognition start error:', e); }
            }

            const voiceInd = document.getElementById('voiceIndicator');
            if (voiceInd) {
                voiceInd.classList.remove('processing');
                voiceInd.classList.add('active');
                const statusText = voiceInd.querySelector('.voice-status-text');
                if (statusText) statusText.textContent = 'Listening...';
            }

            this.mediaRecorder.start();
            this.isRecording = true;
            this.voiceBtn.classList.add('recording');
            KaizenApp.isRecording = true;

            showToast('Recording… Click again to stop.', 'info', 2000);
        } catch (error) {
            showToast('Could not access microphone. Please check permissions.', 'error');
            console.error('Microphone error:', error);
        }
    },

    stopRecording() {
        if (this.isRecording) {
            this.isRecording = false;
            this.voiceBtn.classList.remove('recording');
            this.voiceBtn.classList.remove('processing');
            KaizenApp.isRecording = false;
            this.hideVoiceIndicator();

            if (this.recognition) {
                try {
                    this.recognition.stop();
                } catch (e) {
                    console.warn('SpeechRecognition stop error:', e);
                }
            }

            if (this.mediaRecorder) {
                // Desktop: Stop MediaRecorder, which triggers onstop
                this._manualStop = true;
                this.mediaRecorder.stop();
            } else {
                // Mobile (SpeechRecognition only): Process the transcribed text
                const transcribedText = (this.liveTranscript || this.recognitionTranscript).trim();
                const inputField = document.getElementById('messageInput');
                
                if (transcribedText) {
                    if (inputField) {
                        inputField.value = transcribedText;
                        if (typeof ChatModule !== 'undefined') {
                            if (ChatModule.autoResize) ChatModule.autoResize();
                            // Automatically submit the message
                            ChatModule.sendMessage();
                        }
                    }
                } else {
                    showToast('No speech detected. Please try again.', 'warning', 3000);
                }
            }
        }
    },

    // ══════════════════════════════════════════════════════════════════════
    //  VOICE OVERLAY UTILS
    // ══════════════════════════════════════════════════════════════════════

    hideVoiceIndicator() {
        const voiceInd = document.getElementById('voiceIndicator');
        if (voiceInd) {
            voiceInd.classList.remove('active');
            voiceInd.classList.remove('processing');
            const statusText = voiceInd.querySelector('.voice-status-text');
            if (statusText) statusText.textContent = 'Listening...';
        }
        if (this.voiceBtn) {
            this.voiceBtn.classList.remove('processing');
        }
    },

    // ══════════════════════════════════════════════════════════════════════
    //  PROCESS RECORDED AUDIO
    // ══════════════════════════════════════════════════════════════════════

    async processRecording() {
        try {
            const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
            const formData  = new FormData();
            formData.append('audio', audioBlob, 'recording.webm');

            // Call the full voice-chat pipeline endpoint
            const response = await apiRequest('/api/voice/chat', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error("Backend voice chat API failed");
            }

            const data = await response.json();

            this.hideVoiceIndicator();

            // Clear input field
            const inputField = document.getElementById('messageInput');
            if (inputField) {
                inputField.value = '';
                if (typeof ChatModule !== 'undefined' && ChatModule.autoResize) {
                    ChatModule.autoResize();
                }
            }

            // Transition away from welcome screen
            const welcomeMsg = document.getElementById('welcomeMessage');
            if (welcomeMsg) welcomeMsg.style.display = 'none';

            // Render user's transcribed text
            ChatModule.appendMessage('user', data.transcription);
            KaizenApp.conversationHistory.push({
                role: 'user',
                content: data.transcription,
            });

            // Render AI response with typing animation
            await ChatModule.appendMessageWithTypingEffect(
                'assistant',
                data.response,
                data.sources || []
            );
            KaizenApp.conversationHistory.push({
                role: 'assistant',
                content: data.response,
            });

            // Play synthesized audio response
            if (data.audio_base64) {
                this.playAudioBase64(data.audio_base64);
            }
        } catch (error) {
            console.warn('Backend voice chat failed, falling back to browser-based STT & TTS:', error);
            this.hideVoiceIndicator();
            
            // Fallback flow using browser's transcription (SpeechRecognition)
            const textQuery = (this.liveTranscript || this.recognitionTranscript).trim();
            if (textQuery) {
                
                // Hide welcome screen
                const welcomeMsg = document.getElementById('welcomeMessage');
                if (welcomeMsg) welcomeMsg.style.display = 'none';
                
                // Render user message
                ChatModule.appendMessage('user', textQuery);
                KaizenApp.conversationHistory.push({ role: 'user', content: textQuery });
                
                // Clear input field
                const inputField = document.getElementById('messageInput');
                if (inputField) {
                    inputField.value = '';
                    if (typeof ChatModule !== 'undefined' && ChatModule.autoResize) {
                        ChatModule.autoResize();
                    }
                }
                
                // Show typing indicator
                ChatModule.showTypingIndicator();
                
                try {
                    // Send to standard text chat API
                    const chatResponse = await apiRequest('/api/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            message: textQuery,
                            conversation_history: KaizenApp.conversationHistory.slice(-10),
                        }),
                    });
                    
                    const chatData = await chatResponse.json();
                    ChatModule.hideTypingIndicator();
                    
                    // Render AI response
                    await ChatModule.appendMessageWithTypingEffect(
                        'assistant',
                        chatData.response,
                        chatData.sources || []
                    );
                    KaizenApp.conversationHistory.push({
                        role: 'assistant',
                        content: chatData.response,
                    });
                    
                    // Speak response using Edge TTS instead of robotic browser voice
                    this.synthesizeAndPlay(chatData.response);
                    
                } catch (chatErr) {
                    ChatModule.hideTypingIndicator();
                    showToast(chatErr.message || 'Chat request failed', 'error');
                }
            } else {
                this.voiceBtn.classList.remove('processing');
                showToast('Could not process voice input. Please try typing your message.', 'error');
            }
        }
    },

    // ══════════════════════════════════════════════════════════════════════
    //  TEXT-TO-SPEECH
    // ══════════════════════════════════════════════════════════════════════

    async synthesizeAndPlay(text) {
        try {
            const response = await apiRequest('/api/voice/synthesize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text }),
            });

            if (!response.ok) {
                throw new Error("Backend TTS failed");
            }

            const audioBlob = await response.blob();
            const audioUrl  = URL.createObjectURL(audioBlob);
            this.playAudioUrl(audioUrl);
        } catch (error) {
            console.warn('Backend TTS failed, falling back to browser SpeechSynthesis:', error.message);
            this.playBrowserTTS(text);
        }
    },

    playBrowserTTS(text) {
        this.stopAudio();
        if ('speechSynthesis' in window) {
            this.lastAudioUrl = null;
            this.lastSynthesizedText = text;

            // Clean up text (remove markdown markers like *, #, `, etc.)
            const cleanText = text.replace(/[*#`_\-]/g, '').trim();
            const utterance = new SpeechSynthesisUtterance(cleanText);
            
            // Try to find a nice female English voice
            const voices = window.speechSynthesis.getVoices();
            const preferredVoice = voices.find(v => 
                (v.name.includes('Google US English') || v.name.includes('Microsoft Zira') || v.lang.startsWith('en-US'))
            ) || voices.find(v => v.lang.startsWith('en'));
            
            if (preferredVoice) {
                utterance.voice = preferredVoice;
            }
            
            utterance.rate = 1.0;
            utterance.pitch = 1.0;

            const sidebar = document.getElementById('sidebar');
            if (sidebar) sidebar.classList.add('speaking');

            this.showAudioControls();
            const progressBar = document.getElementById('audioProgressBar');
            if (progressBar) progressBar.style.width = '0%';

            utterance.onboundary = (event) => {
                if (progressBar && cleanText.length) {
                    const pct = (event.charIndex / cleanText.length) * 100;
                    progressBar.style.width = pct + '%';
                }
            };

            utterance.onend = () => {
                if (progressBar) progressBar.style.width = '100%';
                if (sidebar) sidebar.classList.remove('speaking');
                this.hideAudioControls();
            };

            utterance.onerror = () => {
                if (sidebar) sidebar.classList.remove('speaking');
                this.hideAudioControls();
            };

            this.currentUtterance = utterance;
            window.speechSynthesis.speak(utterance);
        } else {
            console.warn('Browser does not support SpeechSynthesis');
        }
    },

    // ══════════════════════════════════════════════════════════════════════
    //  AUDIO PLAYBACK
    // ══════════════════════════════════════════════════════════════════════

    playAudioBase64(base64) {
        const byteChars = atob(base64);
        const byteArray = new Uint8Array(byteChars.length);
        for (let i = 0; i < byteChars.length; i++) {
            byteArray[i] = byteChars.charCodeAt(i);
        }
        const blob = new Blob([byteArray], { type: 'audio/mpeg' });
        const url  = URL.createObjectURL(blob);
        this.playAudioUrl(url);
    },

    playAudioUrl(url) {
        // Stop any currently-playing audio first
        this.stopAudio();

        const sidebar = document.getElementById('sidebar');
        if (sidebar) sidebar.classList.add('speaking');

        this.currentAudio = new Audio(url);
        this.lastAudioUrl = url;
        this.currentAudio.play().catch((err) => {
            console.warn('Audio playback blocked:', err.message);
            if (sidebar) sidebar.classList.remove('speaking');
        });

        this.showAudioControls();

        // Update progress bar during playback
        this.currentAudio.ontimeupdate = () => {
            const progressBar = document.getElementById('audioProgressBar');
            if (progressBar && this.currentAudio.duration) {
                const pct =
                    (this.currentAudio.currentTime / this.currentAudio.duration) * 100;
                progressBar.style.width = pct + '%';
            }
        };

        this.currentAudio.onended = () => {
            const progressBar = document.getElementById('audioProgressBar');
            if (progressBar) progressBar.style.width = '100%';
            if (sidebar) sidebar.classList.remove('speaking');
            this.hideAudioControls();
        };
    },

    stopAudio() {
        if (this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio.currentTime = 0;
        }
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
        }
        const sidebar = document.getElementById('sidebar');
        if (sidebar) sidebar.classList.remove('speaking');
        this.hideAudioControls();
    },

    replayAudio() {
        if (this.lastAudioUrl) {
            this.playAudioUrl(this.lastAudioUrl);
        } else if (this.lastSynthesizedText) {
            this.playBrowserTTS(this.lastSynthesizedText);
        }
    },

    showAudioControls() {
        if (this.audioControls) {
            this.audioControls.classList.remove('hidden');
        }
    },

    hideAudioControls() {
        if (this.audioControls) {
            this.audioControls.classList.add('hidden');
        }
    },
};
