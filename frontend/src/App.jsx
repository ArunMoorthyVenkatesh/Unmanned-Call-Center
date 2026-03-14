import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import './App.css';
import AppointmentDashboard from './components/AppointmentDashboard';

// --- Configuration ---
// const API_BASE_URL = '/api';
const API_BASE_URL = 'http://localhost:8000';
const API_KEY = 'nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM';
const HEADERS = { 'X-API-Key': API_KEY };

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function App() {
  const [activeTab, setActiveTab]       = useState('chat');
  const [commandText, setCommandText]   = useState('');
  const [chatHistory, setChatHistory]   = useState([]);
  const [isLoading, setIsLoading]       = useState(false);
  const [error, setError]               = useState('');
  const [langChoice, setLangChoice]     = useState('en');
  const [sessionId, setSessionId]       = useState(() =>
    'session-' + Date.now() + '-' + Math.random().toString(36).slice(2, 9)
  );

  // Recording state
  const [isRecording, setIsRecording]       = useState(false);
  const [isAudioSupported, setIsAudioSupported] = useState(false);
  const [recordingTime, setRecordingTime]   = useState(0);

  // Refs
  const mediaRecorderRef   = useRef(null);
  const audioChunksRef     = useRef([]);
  const recordingTimerRef  = useRef(null);
  const messagesEndRef     = useRef(null);
  const timeoutRef         = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, isLoading]);

  // Check audio support
  useEffect(() => {
    const ok =
      !!(navigator.mediaDevices?.getUserMedia) &&
      !!window.MediaRecorder &&
      ['audio/webm', 'audio/mp4', 'audio/ogg', 'audio/wav'].some(f =>
        MediaRecorder.isTypeSupported(f)
      );
    setIsAudioSupported(ok);
  }, []);

  // Cleanup on unmount
  useEffect(() => () => {
    if (isRecording && mediaRecorderRef.current) mediaRecorderRef.current.stop();
    clearInterval(recordingTimerRef.current);
    clearTimeout(timeoutRef.current);
  }, [isRecording]);

  // ── Reset conversation ──
  const resetChat = useCallback(async () => {
    try {
      await axios.post(`${API_BASE_URL}/reset-conversation/${sessionId}`, {}, { headers: HEADERS });
    } catch (_) {}
    const newId = 'session-' + Date.now() + '-' + Math.random().toString(36).slice(2, 9);
    setSessionId(newId);
    setChatHistory([]);
    setCommandText('');
    setError('');
    clearTimeout(timeoutRef.current);
  }, [sessionId]);

  // ── TTS ──
  const speakText = useCallback((text) => {
    if (!text || !('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const utt = new SpeechSynthesisUtterance(text);
    utt.lang  = langChoice === 'th' ? 'th-TH' : 'en-US';
    utt.rate  = 0.9;
    const voices = window.speechSynthesis.getVoices();
    const voice  = voices.find(v =>
      langChoice === 'th'
        ? v.lang.toLowerCase().includes('th')
        : v.lang.toLowerCase().startsWith('en')
    );
    if (voice) utt.voice = voice;
    window.speechSynthesis.speak(utt);
  }, [langChoice]);

  // ── Send text command ──
  const handleSubmit = useCallback(async (e, textOverride) => {
    if (e) e.preventDefault();
    const text = textOverride !== undefined ? textOverride : commandText;
    if (!text.trim()) return;

    setIsLoading(true);
    setError('');
    setChatHistory(prev => [...prev, { sender: 'user', text, time: new Date() }]);
    setCommandText('');

    try {
      const fd = new FormData();
      fd.append('command_text', text);
      fd.append('session_id',   sessionId);
      fd.append('langChoice',   langChoice);

      const { data } = await axios.post(`${API_BASE_URL}/process-command-unified/`, fd, {
        headers: { ...HEADERS, 'Content-Type': 'multipart/form-data' },
      });

      if (data?.reply) {
        setChatHistory(prev => [...prev, {
          sender:         'assistant',
          text:           data.reply,
          command:        data.command,
          openEndedValue: data.openEndedValue,
          time:           new Date(),
        }]);
        speakText(data.reply);
      }
    } catch (err) {
      const msg = err.response?.data?.reply || err.message || 'Request failed.';
      setError(msg);
      setChatHistory(prev => [...prev, { sender: 'assistant', text: `Error: ${msg}`, time: new Date() }]);
    } finally {
      setIsLoading(false);
    }
  }, [commandText, sessionId, langChoice, speakText]);

  // ── Key handler ──
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(e); }
  };

  // ── Recording ──
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true }
      }).catch(() => navigator.mediaDevices.getUserMedia({ audio: true }));

      const fmt = ['audio/webm;codecs=opus','audio/webm','audio/mp4','audio/ogg','audio/wav']
        .find(f => MediaRecorder.isTypeSupported(f)) || 'audio/webm';

      audioChunksRef.current = [];
      mediaRecorderRef.current = new MediaRecorder(stream, { mimeType: fmt });

      let chunkIdx = 0;
      let silenceCount = 0;
      let stopped = false;

      mediaRecorderRef.current.ondataavailable = async (ev) => {
        if (ev.data.size > 0) {
          audioChunksRef.current.push(ev.data);
          // VAD check
          if (!stopped) {
            try {
              const fd = new FormData();
              fd.append('session_id',      sessionId);
              fd.append('audio_chunk',     ev.data);
              fd.append('chunk_index',     chunkIdx.toString());
              fd.append('silence_threshold','1000');
              const { data } = await axios.post(`${API_BASE_URL}/voice/stream-audio-chunk`, fd, {
                headers: { ...HEADERS, 'Content-Type': 'multipart/form-data' },
                timeout: 2000,
              });
              if (data.is_silence || data.volume < 1000) silenceCount++;
              else silenceCount = 0;
              if (silenceCount >= 2 && chunkIdx >= 3) {
                stopped = true;
                stopRecording();
              }
            } catch (_) {}
          }
          chunkIdx++;
        }
      };

      mediaRecorderRef.current.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(audioChunksRef.current, { type: fmt });
        await sendAudio(blob, fmt);
      };

      mediaRecorderRef.current.start(1000);
      setIsRecording(true);
      setRecordingTime(0);
      setError('');
      recordingTimerRef.current = setInterval(() => setRecordingTime(t => t + 1), 1000);
    } catch (err) {
      const msg = err.name === 'NotAllowedError'
        ? 'Microphone permission denied. Please allow access and try again.'
        : err.name === 'NotFoundError'
          ? 'No microphone found. Please connect one.'
          : 'Could not access microphone.';
      setError(msg);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
    clearInterval(recordingTimerRef.current);
    recordingTimerRef.current = null;
  };

  const sendAudio = async (blob, fmt) => {
    setIsLoading(true);
    setError('');
    try {
      const ext  = fmt.includes('mp4') ? 'mp4' : fmt.includes('ogg') ? 'ogg' : fmt.includes('wav') ? 'wav' : 'webm';
      const fd   = new FormData();
      fd.append('audio_file', blob, `recording.${ext}`);
      fd.append('session_id', sessionId);
      fd.append('langChoice', langChoice);

      const { data } = await axios.post(`${API_BASE_URL}/process-command-unified/`, fd, {
        headers: { ...HEADERS, 'Content-Type': 'multipart/form-data' },
        timeout: 30000,
      });

      if (data.transcribed_text) {
        setChatHistory(prev => [...prev, { sender: 'user', text: data.transcribed_text, time: new Date() }]);
      }
      if (data.reply) {
        setChatHistory(prev => [...prev, {
          sender:         'assistant',
          text:           data.reply,
          command:        data.command,
          openEndedValue: data.openEndedValue,
          time:           new Date(),
        }]);
        speakText(data.reply);
      }
    } catch (err) {
      const msg = err.response?.data?.reply || err.message || 'Audio processing failed.';
      setError(msg);
    } finally {
      setIsLoading(false);
      setRecordingTime(0);
    }
  };

  // ── Render ──
  return (
    <div className="app-shell">

      {/* ── Top Nav ── */}
      <nav className="top-nav">
        <div className="nav-brand">
          <div className="nav-logo">🚗</div>
          <div>
            <div className="nav-title">Toyota Unmanned Service Center</div>
            <div className="nav-subtitle">AI-Powered Call Center</div>
          </div>
        </div>

        <div className="nav-tabs">
          <button
            className={`nav-tab ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            <span className="tab-icon">💬</span> Chat
          </button>
          <button
            className={`nav-tab ${activeTab === 'appointments' ? 'active' : ''}`}
            onClick={() => setActiveTab('appointments')}
          >
            <span className="tab-icon">📅</span> Appointments
          </button>
        </div>
      </nav>

      {/* ── Main ── */}
      <main className="main-content">

        {/* ── Chat Tab ── */}
        {activeTab === 'chat' && (
          <div className="chat-page">
            <div className="chat-card">

              {/* Chat header */}
              <div className="chat-header">
                <div className="chat-header-info">
                  <div className="assistant-avatar">🤖</div>
                  <div>
                    <div className="assistant-name">Toyota AI Assistant</div>
                    <div className="assistant-status">
                      <span className="status-dot" />
                      Online · Gemini 2.5
                    </div>
                  </div>
                </div>

                <div className="chat-controls">
                  {/* Language toggle */}
                  <div className="lang-toggle">
                    <button
                      className={`lang-btn ${langChoice === 'en' ? 'active' : ''}`}
                      onClick={() => setLangChoice('en')}
                    >EN</button>
                    <button
                      className={`lang-btn ${langChoice === 'th' ? 'active' : ''}`}
                      onClick={() => setLangChoice('th')}
                    >TH</button>
                  </div>

                  {/* Reset */}
                  <button className="reset-btn" onClick={resetChat} title="Reset conversation">
                    ↺ Reset
                  </button>
                </div>
              </div>

              {/* Messages */}
              <div className="messages-window">
                {chatHistory.length === 0 && !isLoading && (
                  <div className="empty-state">
                    <div className="empty-icon">🚗</div>
                    <div className="empty-text">How can I help you today?</div>
                    <div className="empty-hint">
                      Try "Turn on the AC", "Navigate to downtown", or ask about your car.
                    </div>
                  </div>
                )}

                {chatHistory.map((msg, i) => (
                  <div key={i} className={`msg-row ${msg.sender}`}>
                    <div className={`msg-avatar ${msg.sender}`}>
                      {msg.sender === 'assistant' ? '🤖' : '👤'}
                    </div>
                    <div className="msg-body">
                      <div className="msg-bubble">
                        {msg.text}
                        {msg.sender === 'assistant' && (msg.command || msg.openEndedValue) && (
                          <div className="cmd-details">
                            {msg.command && (
                              <span className="cmd-tag">⚙️ Code: {msg.command}</span>
                            )}
                            {msg.openEndedValue != null && (
                              <span className="cmd-tag">📌 Value: {msg.openEndedValue}</span>
                            )}
                          </div>
                        )}
                      </div>
                      <span className="msg-time">{msg.time ? formatTime(msg.time) : ''}</span>
                    </div>
                  </div>
                ))}

                {isLoading && (
                  <div className="typing-row">
                    <div className="msg-avatar assistant">🤖</div>
                    <div className="typing-bubble">
                      <div className="typing-dot" />
                      <div className="typing-dot" />
                      <div className="typing-dot" />
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Error banner */}
              {error && (
                <div className="error-banner">
                  ⚠️ {error}
                </div>
              )}

              {/* Input bar */}
              <div className="input-bar">
                <input
                  className="text-input"
                  type="text"
                  value={commandText}
                  onChange={e => setCommandText(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    isRecording
                      ? `Recording… ${recordingTime}s`
                      : 'Type a command or speak…'
                  }
                  disabled={isLoading || isRecording}
                />

                {/* Mic button */}
                <button
                  className={`mic-btn ${isRecording ? 'recording' : ''}`}
                  onClick={isRecording ? stopRecording : startRecording}
                  disabled={isLoading || !isAudioSupported}
                  title={
                    !isAudioSupported
                      ? 'Microphone unavailable'
                      : isRecording ? 'Stop recording' : 'Start recording'
                  }
                >
                  {isRecording ? '⏹' : '🎙'}
                  {isRecording && <span className="rec-timer">{recordingTime}s</span>}
                </button>

                {/* Send button */}
                <button
                  className="send-btn"
                  onClick={handleSubmit}
                  disabled={isLoading || isRecording || !commandText.trim()}
                  title="Send"
                >
                  ➤
                </button>
              </div>

              {/* Session bar */}
              <div className="session-bar">
                <span>Session: <span className="session-id-text">{sessionId.slice(-12)}</span></span>
                <span>{chatHistory.length} messages · {langChoice === 'en' ? 'English' : 'Thai'}</span>
              </div>
            </div>
          </div>
        )}

        {/* ── Appointments Tab ── */}
        {activeTab === 'appointments' && (
          <div className="appointments-page">
            <AppointmentDashboard />
          </div>
        )}

      </main>
    </div>
  );
}

export default App;
