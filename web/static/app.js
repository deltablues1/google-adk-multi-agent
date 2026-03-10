/**
 * Google Workspace ADK - Dashboard Application
 * Alpine.js reactive component for chat, trace, and monitoring.
 * Supports image/file uploads and inline image rendering.
 */

function dashboard() {
    return {
        // Chat state
        inputMessage: '',
        messages: [],
        streaming: false,
        streamBuffer: '',

        // File upload state
        pendingFiles: [],   // [{file, previewUrl, uploading, uploaded: {file_id, url, ...}}]
        dragOver: false,

        // Image modal
        imageModal: null,

        // Session state
        sessions: [],
        currentSessionId: null,
        userId: 'web-user',

        // System state
        agents: [],
        systemStatus: {},
        traceEvents: [],

        // Voice state
        voiceEnabled: false,
        voiceListening: false,
        voiceSupported: false,
        ttsSupported: false,
        _recognition: null,
        _voiceAutoSend: false,

        // Polling
        _statusInterval: null,

        async init() {
            // Load initial data in parallel
            await Promise.all([
                this.loadAgents(),
                this.loadSessions(),
                this.loadStatus()
            ]);

            // Auto-create first session if none exist
            if (this.sessions.length === 0) {
                await this.newSession();
            }

            // Poll status every 15 seconds
            this._statusInterval = setInterval(() => this.loadStatus(), 15000);

            // Initialize voice
            this.initVoice();

            // Focus input
            this.$nextTick(() => {
                if (this.$refs.chatInput) this.$refs.chatInput.focus();
            });
        },

        // === Data Loading ===

        async loadAgents() {
            try {
                const res = await fetch('/api/agents');
                if (res.ok) this.agents = await res.json();
            } catch (e) {
                console.error('Failed to load agents:', e);
            }
        },

        async loadSessions() {
            try {
                const res = await fetch('/api/sessions');
                if (res.ok) this.sessions = await res.json();
            } catch (e) {
                console.error('Failed to load sessions:', e);
            }
        },

        async loadStatus() {
            try {
                const res = await fetch('/api/status');
                if (res.ok) this.systemStatus = await res.json();
            } catch (e) {
                console.error('Failed to load status:', e);
            }
        },

        async loadHistory(sessionId) {
            try {
                const [histRes, traceRes] = await Promise.all([
                    fetch(`/api/sessions/${sessionId}/history`),
                    fetch(`/api/trace/${sessionId}`)
                ]);
                if (histRes.ok) this.messages = await histRes.json();
                if (traceRes.ok) this.traceEvents = await traceRes.json();
                this.scrollToBottom();
            } catch (e) {
                console.error('Failed to load history:', e);
            }
        },

        // === Session Management ===

        async switchSession(session) {
            this.currentSessionId = session.session_id;
            await fetch(`/api/sessions/${session.session_id}/switch?user_id=${this.userId}`, {
                method: 'POST'
            });
            await this.loadHistory(session.session_id);
            await this.loadSessions();
        },

        async newSession() {
            try {
                const res = await fetch(`/api/sessions/new?user_id=${this.userId}`, {
                    method: 'POST'
                });
                if (res.ok) {
                    const data = await res.json();
                    this.currentSessionId = data.session_id;
                    this.messages = [];
                    this.traceEvents = [];
                    await this.loadSessions();
                }
            } catch (e) {
                console.error('Failed to create session:', e);
            }
        },

        // === File Upload ===

        handleFileSelect(event) {
            const files = event.target.files;
            if (files) this.addFiles(files);
            event.target.value = '';  // reset so same file can be re-selected
        },

        handleDrop(event) {
            this.dragOver = false;
            const files = event.dataTransfer.files;
            if (files) this.addFiles(files);
        },

        addFiles(fileList) {
            for (const file of fileList) {
                // Validate type
                const allowed = ['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/bmp', 'application/pdf'];
                if (!allowed.includes(file.type)) {
                    console.warn(`Skipping unsupported file type: ${file.type}`);
                    continue;
                }

                // Create preview URL for images
                let previewUrl = null;
                if (file.type.startsWith('image/')) {
                    previewUrl = URL.createObjectURL(file);
                }

                this.pendingFiles.push({
                    file: file,
                    previewUrl: previewUrl,
                    uploading: false,
                    uploaded: null,
                });
            }
        },

        removePendingFile(idx) {
            const pf = this.pendingFiles[idx];
            if (pf.previewUrl) URL.revokeObjectURL(pf.previewUrl);
            this.pendingFiles.splice(idx, 1);
        },

        async uploadPendingFiles() {
            /**
             * Upload all pending files to /api/upload.
             * Returns array of upload results.
             */
            const results = [];
            for (const pf of this.pendingFiles) {
                if (pf.uploaded) {
                    results.push(pf.uploaded);
                    continue;
                }

                pf.uploading = true;
                try {
                    const formData = new FormData();
                    formData.append('file', pf.file);
                    formData.append('user_id', this.userId);
                    formData.append('session_id', this.currentSessionId || '');

                    const res = await fetch('/api/upload', {
                        method: 'POST',
                        body: formData
                    });

                    if (!res.ok) {
                        const err = await res.json();
                        throw new Error(err.detail || 'Upload failed');
                    }

                    const data = await res.json();
                    pf.uploaded = data;
                    results.push(data);
                } catch (e) {
                    console.error('Upload error:', e);
                    results.push({ error: e.message });
                } finally {
                    pf.uploading = false;
                }
            }
            return results;
        },

        // === Chat ===

        async sendMessage() {
            const message = this.inputMessage.trim();
            const hasFiles = this.pendingFiles.length > 0;
            if (!message && !hasFiles) return;
            if (this.streaming) return;

            this.inputMessage = '';
            this.streaming = true;
            this.streamBuffer = '';

            // Upload files first if any
            let uploadedFiles = [];
            let attachments = [];
            if (hasFiles) {
                uploadedFiles = await this.uploadPendingFiles();
                attachments = uploadedFiles
                    .filter(f => !f.error)
                    .map(f => ({
                        file_id: f.file_id,
                        filename: f.filename,
                        mime_type: f.mime_type,
                        url: f.url,
                    }));
            }

            // Build the message to send to the agent
            // If there are uploaded files, prepend file references
            let agentMessage = message;
            if (uploadedFiles.length > 0) {
                const fileRefs = uploadedFiles
                    .filter(f => !f.error)
                    .map(f => `[ATTACHED_FILE: file_id=${f.file_id}, name=${f.filename}, type=${f.mime_type}, base64_length=${f.base64?.length || 0}]`)
                    .join('\n');
                agentMessage = fileRefs + (message ? '\n\n' + message : '\n\nAnalyse the attached file(s).');
            }

            // Add user message to UI immediately
            this.messages.push({
                role: 'user',
                content: message || '(attached file)',
                attachments: attachments,
                timestamp: Date.now() / 1000
            });
            this.scrollToBottom();

            // Clean up pending files
            for (const pf of this.pendingFiles) {
                if (pf.previewUrl) URL.revokeObjectURL(pf.previewUrl);
            }
            this.pendingFiles = [];

            try {
                // Build request body - include file data for multimodal processing
                const requestBody = {
                    message: agentMessage,
                    user_id: this.userId,
                    session_id: this.currentSessionId,
                };

                // If we have uploaded files, include their base64 for the agent
                if (uploadedFiles.length > 0) {
                    requestBody.attachments = uploadedFiles
                        .filter(f => !f.error)
                        .map(f => ({
                            file_id: f.file_id,
                            mime_type: f.mime_type,
                            base64: f.base64,
                        }));
                }

                const response = await fetch('/api/chat/stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                // Parse SSE stream
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let currentEventType = 'text';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (line.startsWith('event:')) {
                            currentEventType = line.substring(6).trim();
                        } else if (line.startsWith('data:')) {
                            const rawData = line.substring(5).trim();
                            if (rawData) {
                                this.handleSSEEvent(currentEventType, rawData);
                            }
                        }
                    }
                }

            } catch (err) {
                console.error('Stream error:', err);
                this.streamBuffer += '\n[Error: ' + err.message + ']';
            }

            // Finalize: move stream buffer into messages
            if (this.streamBuffer) {
                // TTS: read response aloud if enabled
                this.speakText(this.streamBuffer);

                this.messages.push({
                    role: 'assistant',
                    content: this.streamBuffer,
                    timestamp: Date.now() / 1000
                });
            }

            this.streaming = false;
            this.streamBuffer = '';
            this.scrollToBottom();

            // Refresh sessions list
            await this.loadSessions();

            // Refocus input
            this.$nextTick(() => {
                if (this.$refs.chatInput) this.$refs.chatInput.focus();
            });
        },

        handleSSEEvent(eventType, rawData) {
            switch (eventType) {
                case 'text':
                    this.streamBuffer += rawData;
                    this.scrollToBottom();
                    break;

                case 'image':
                    // Agent sent an inline image or video - render it
                    try {
                        const imgData = JSON.parse(rawData);
                        const tag = imgData.type === 'video' ? 'VIDEO' : 'IMAGE';
                        const mediaTag = `[${tag}:${imgData.url}:${imgData.alt || 'Generated media'}]`;
                        // Avoid duplicate tags (agent text may already contain the tag)
                        if (!this.streamBuffer.includes(mediaTag)) {
                            this.streamBuffer += `\n${mediaTag}\n`;
                        }
                        this.scrollToBottom();
                    } catch (e) {
                        console.warn('Failed to parse image event:', e);
                    }
                    break;

                case 'tool_call':
                case 'tool_response':
                    try {
                        const traceEntry = JSON.parse(rawData);
                        this.traceEvents.push(traceEntry);
                    } catch (e) { /* ignore parse errors */ }
                    break;

                case 'done':
                    try {
                        const doneData = JSON.parse(rawData);
                        if (doneData.session_id && !this.currentSessionId) {
                            this.currentSessionId = doneData.session_id;
                        }
                    } catch (e) { /* ignore */ }
                    break;

                case 'error':
                    this.streamBuffer += '\n[Error: ' + rawData + ']';
                    break;
            }
        },

        // === Image Modal ===

        openImageModal(url) {
            this.imageModal = url;
        },

        // === Formatting ===

        formatMessage(text) {
            if (!text) return '';

            // Debug: log if text contains media tags
            if (text.includes('[VIDEO:') || text.includes('[IMAGE:')) {
                console.log('formatMessage input contains media tag:', text.substring(text.indexOf('['), text.indexOf(']', text.indexOf('[')) + 1));
            }

            // Escape HTML
            let safe = text
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');

            // === MEDIA TAGS - process BEFORE any other markdown ===

            // Inline videos [VIDEO:url:alt] - MUST be before IMAGE to avoid conflicts
            safe = safe.replace(/\[VIDEO:(\/api\/media\/[^\]:]+|https?:\/\/[^\]:]+):([^\]]*)\]/g,
                '<div class="chat-video"><video src="$1" controls preload="metadata"></video><div class="chat-image-caption">$2</div></div>');

            // GCS video references
            safe = safe.replace(/\[VIDEO:(gs:\/\/[^\]:]+):([^\]]*)\]/g,
                '<div class="chat-video"><em>Video stored at: $1</em><div class="chat-image-caption">$2</div></div>');

            // Inline images [IMAGE:url:alt]
            safe = safe.replace(/\[IMAGE:(\/api\/media\/[^\]:]+|https?:\/\/[^\]:]+):([^\]]*)\]/g,
                '<div class="chat-image"><img src="$1" alt="$2" loading="lazy" onclick="document.querySelector(\'[x-data]\')._x_dataStack[0].openImageModal(\'$1\')"><div class="chat-image-caption">$2</div></div>');

            // GCS image references (fallback - show placeholder)
            safe = safe.replace(/\[IMAGE:(gs:\/\/[^\]:]+):([^\]]*)\]/g,
                '<div class="chat-image"><em>Image stored at: $1</em><div class="chat-image-caption">$2</div></div>');

            // Fallback: markdown links to /api/media/ rendered as images
            safe = safe.replace(/\[([^\]]*)\]\((\/api\/media\/[^)]+)\)/g,
                '<div class="chat-image"><img src="$2" alt="$1" loading="lazy" onclick="document.querySelector(\'[x-data]\')._x_dataStack[0].openImageModal(\'$2\')"><div class="chat-image-caption">$1</div></div>');

            // Fallback: bare /api/media/ URLs on their own line
            safe = safe.replace(/(?:^|\n)(\/api\/media\/\S+)(?:\n|$)/gm,
                '\n<div class="chat-image"><img src="$1" alt="Generated image" loading="lazy" onclick="document.querySelector(\'[x-data]\')._x_dataStack[0].openImageModal(\'$1\')"><div class="chat-image-caption">Generated image</div></div>\n');

            // Code blocks ```...```
            safe = safe.replace(/```(\w*)\n?([\s\S]*?)```/g,
                '<pre><code>$2</code></pre>');

            // Inline code `...`
            safe = safe.replace(/`([^`]+)`/g, '<code>$1</code>');

            // GCS storage links - replace with "image not publicly accessible" notice
            safe = safe.replace(/\[([^\]]*)\]\((https?:\/\/storage\.googleapis\.com\/[^)]+)\)/g,
                '<em class="text-muted">(Image generated but GCS link not publicly accessible)</em>');

            // Links [text](url)
            safe = safe.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
                '<a href="$2" target="_blank" rel="noopener">$1</a>');

            // Bold **...**
            safe = safe.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

            // Italic *...*
            safe = safe.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');

            // Status badges [Završeno] / [OK] / [Greška]
            safe = safe.replace(/\[(Zavr[sš]eno|OK|Uspje[sš]no)\]/gi,
                '<span class="badge badge-success">$1</span>');
            safe = safe.replace(/\[(Gre[sš]ka|Error|FAILED)\]/gi,
                '<span class="badge badge-error">$1</span>');
            safe = safe.replace(/\[(Info|Napomena)\]/gi,
                '<span class="badge badge-info">$1</span>');

            // Process line by line for lists and paragraphs
            const lines = safe.split('\n');
            let html = '';
            let inList = false;
            let listType = null;

            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim();

                // Numbered list: 1. item or 1) item
                const olMatch = line.match(/^(\d+)[.)]\s+(.+)/);
                // Bullet list: - item or * item
                const ulMatch = line.match(/^[-*]\s+(.+)/);

                if (olMatch) {
                    if (!inList || listType !== 'ol') {
                        if (inList) html += listType === 'ol' ? '</ol>' : '</ul>';
                        html += '<ol>';
                        inList = true;
                        listType = 'ol';
                    }
                    html += '<li>' + olMatch[2] + '</li>';
                } else if (ulMatch) {
                    if (!inList || listType !== 'ul') {
                        if (inList) html += listType === 'ol' ? '</ol>' : '</ul>';
                        html += '<ul>';
                        inList = true;
                        listType = 'ul';
                    }
                    html += '<li>' + ulMatch[1] + '</li>';
                } else {
                    // Close any open list
                    if (inList) {
                        html += listType === 'ol' ? '</ol>' : '</ul>';
                        inList = false;
                        listType = null;
                    }

                    // Headings ### ...
                    if (line.match(/^#{1,3}\s+/)) {
                        const heading = line.replace(/^#{1,3}\s+/, '');
                        html += '<div class="msg-heading">' + heading + '</div>';
                    } else if (line === '') {
                        html += '<div class="msg-spacer"></div>';
                    } else if (line.startsWith('<div class="chat-image">')) {
                        // Don't wrap images in msg-line
                        html += line;
                    } else {
                        html += '<div class="msg-line">' + line + '</div>';
                    }
                }
            }
            if (inList) {
                html += listType === 'ol' ? '</ol>' : '</ul>';
            }

            return html;
        },

        formatSessionName(session) {
            const idx = this.sessions.indexOf(session);
            const num = this.sessions.length - idx;
            return 'Session ' + num;
        },

        getUtilization(info) {
            if (!info) return 0;
            if (info.project_bucket && typeof info.project_bucket.utilization === 'number') {
                return info.project_bucket.utilization;
            }
            return 0;
        },

        // === Voice ===

        initVoice() {
            // Check TTS support
            this.ttsSupported = 'speechSynthesis' in window;

            // Check STT support
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SpeechRecognition) {
                this.voiceSupported = false;
                return;
            }

            this.voiceSupported = true;
            const recognition = new SpeechRecognition();
            recognition.lang = 'hr-HR';
            recognition.continuous = false;
            recognition.interimResults = true;
            recognition.maxAlternatives = 1;

            recognition.onresult = (event) => {
                let finalTranscript = '';
                let interimTranscript = '';

                for (let i = event.resultIndex; i < event.results.length; i++) {
                    const transcript = event.results[i][0].transcript;
                    if (event.results[i].isFinal) {
                        finalTranscript += transcript;
                    } else {
                        interimTranscript += transcript;
                    }
                }

                if (finalTranscript) {
                    this.inputMessage = finalTranscript;
                    this._voiceAutoSend = true;
                } else if (interimTranscript) {
                    this.inputMessage = interimTranscript;
                }
            };

            recognition.onend = () => {
                this.voiceListening = false;
                if (this._voiceAutoSend && this.inputMessage.trim()) {
                    this._voiceAutoSend = false;
                    this.sendMessage();
                }
            };

            recognition.onerror = (event) => {
                console.error('Speech recognition error:', event.error);
                this.voiceListening = false;
                this._voiceAutoSend = false;

                if (event.error === 'not-allowed') {
                    alert('Mikrofon nije dozvoljen. Omogucite pristup mikrofonu u postavkama preglednika.');
                }
            };

            this._recognition = recognition;
        },

        toggleListening() {
            if (!this._recognition) return;

            if (this.voiceListening) {
                this._recognition.stop();
                this.voiceListening = false;
            } else {
                this._voiceAutoSend = false;
                this.inputMessage = '';
                try {
                    this._recognition.start();
                    this.voiceListening = true;
                } catch (e) {
                    console.error('Failed to start recognition:', e);
                }
            }
        },

        speakText(text) {
            if (!this.ttsSupported || !this.voiceEnabled) return;

            // Stop any current speech
            speechSynthesis.cancel();

            // Clean text for TTS
            let clean = text;
            clean = clean.replace(/\[Error:.*?\]/g, '');
            clean = clean.replace(/\[IMAGE:[^\]]*\]/g, '');
            clean = clean.replace(/\[VIDEO:[^\]]*\]/g, '');
            clean = clean.replace(/\[ATTACHED_FILE:[^\]]*\]/g, '');
            clean = clean.replace(/Error:\s*\d+\s+RESOURCE_EXHAUSTED[^\n]*/g, '');
            clean = clean.replace(/\{[^}]*'error'[^}]*\}/g, '');
            clean = clean.replace(/```[\s\S]*?```/g, '');
            clean = clean.replace(/`[^`]+`/g, '');
            clean = clean.replace(/\*\*(.*?)\*\*/g, '$1');
            clean = clean.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '$1');
            clean = clean.replace(/#{1,3}\s+/g, '');
            clean = clean.replace(/https?:\/\/\S+/g, '');
            clean = clean.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
            clean = clean.replace(/\n{2,}/g, '. ');
            clean = clean.replace(/\n/g, ' ');
            clean = clean.trim();

            if (!clean) return;

            // Split long text into chunks (speechSynthesis has ~200 char limit in some browsers)
            const chunks = [];
            const sentences = clean.split(/(?<=[.!?])\s+/);
            let current = '';

            for (const sentence of sentences) {
                if ((current + ' ' + sentence).length > 180) {
                    if (current) chunks.push(current.trim());
                    current = sentence;
                } else {
                    current += (current ? ' ' : '') + sentence;
                }
            }
            if (current) chunks.push(current.trim());

            // Get Croatian voice
            const voices = speechSynthesis.getVoices();
            const hrVoice = voices.find(v => v.lang.startsWith('hr'));

            // Speak each chunk sequentially
            const speakChunk = (index) => {
                if (index >= chunks.length) return;

                const utterance = new SpeechSynthesisUtterance(chunks[index]);
                utterance.lang = 'hr-HR';
                utterance.rate = 1.0;
                utterance.pitch = 1.0;
                if (hrVoice) utterance.voice = hrVoice;

                utterance.onend = () => speakChunk(index + 1);
                utterance.onerror = () => speakChunk(index + 1);

                speechSynthesis.speak(utterance);
            };

            speakChunk(0);
        },

        stopSpeaking() {
            if (this.ttsSupported) {
                speechSynthesis.cancel();
            }
        },

        scrollToBottom() {
            this.$nextTick(() => {
                const container = this.$refs.messagesContainer;
                if (container) {
                    container.scrollTop = container.scrollHeight;
                }
            });
        }
    };
}
