import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import './App.css';
import AppointmentDashboard from './components/AppointmentDashboard';

const API_BASE_URL = 'http://localhost:8000';
const API_KEY      = 'nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM';
const HEADERS      = { 'X-API-Key': API_KEY };

const fmt = (d) => d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const uid = () => 'session-' + Date.now() + '-' + Math.random().toString(36).slice(2, 9);

/* ─── SVG icons ─────────────────────────────────────────── */
const Icons = {
  logo: (
    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M3 12h3m12 0h3M12 3v3m0 12v3"/></svg>
  ),
  bot: (
    <svg viewBox="0 0 24 24"><rect x="3" y="8" width="18" height="12" rx="3"/><path d="M8 8V6a4 4 0 018 0v2"/><circle cx="9" cy="14" r="1.2" fill="currentColor" stroke="none"/><circle cx="15" cy="14" r="1.2" fill="currentColor" stroke="none"/></svg>
  ),
  user: (
    <svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>
  ),
  chat: (
    <svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
  ),
  calendar: (
    <svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
  ),
  mic: (
    <svg viewBox="0 0 24 24"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0014 0M12 19v3M9 22h6"/></svg>
  ),
  stop: (
    <svg viewBox="0 0 24 24"><rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor" stroke="none"/></svg>
  ),
  send: (
    <svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
  ),
  refresh: (
    <svg viewBox="0 0 24 24"><path d="M1 4v6h6"/><path d="M23 20v-6h-6"/><path d="M20.49 9A9 9 0 005.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 013.51 15"/></svg>
  ),
};

export default function App() {
  const [tab, setTab]             = useState('chat');
  const [text, setText]           = useState('');
  const [msgs, setMsgs]           = useState([]);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState('');
  const [lang, setLang]           = useState('en');
  const [session, setSession]     = useState(uid);
  const [recording, setRecording] = useState(false);
  const [recTime, setRecTime]     = useState(0);
  const [micOk, setMicOk]         = useState(false);

  const recRef    = useRef(null);
  const chunksRef = useRef([]);
  const timerRef  = useRef(null);
  const bottomRef = useRef(null);

  // auto-scroll
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs, loading]);

  // mic support check
  useEffect(() => {
    setMicOk(
      !!(navigator.mediaDevices?.getUserMedia) &&
      !!window.MediaRecorder &&
      ['audio/webm','audio/mp4','audio/ogg','audio/wav'].some(f => MediaRecorder.isTypeSupported(f))
    );
  }, []);

  // cleanup
  useEffect(() => () => {
    clearInterval(timerRef.current);
    if (recRef.current?.state === 'recording') recRef.current.stop();
  }, []);

  const speak = useCallback((t) => {
    if (!t || !('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(t);
    u.lang  = lang === 'th' ? 'th-TH' : 'en-US';
    u.rate  = 0.9;
    const v = window.speechSynthesis.getVoices().find(v =>
      lang === 'th' ? v.lang.includes('th') : v.lang.startsWith('en')
    );
    if (v) u.voice = v;
    window.speechSynthesis.speak(u);
  }, [lang]);

  const addMsg = (msg) => setMsgs(p => [...p, { ...msg, time: new Date() }]);

  const reset = async () => {
    try { await axios.post(`${API_BASE_URL}/reset-conversation/${session}`, {}, { headers: HEADERS }); } catch (_) {}
    setSession(uid());
    setMsgs([]);
    setText('');
    setError('');
  };

  const send = async (e, override) => {
    if (e) e.preventDefault();
    const t = override ?? text;
    if (!t.trim()) return;
    setText('');
    setError('');
    setLoading(true);
    addMsg({ role: 'user', text: t });

    try {
      const fd = new FormData();
      fd.append('command_text', t);
      fd.append('session_id',   session);
      fd.append('langChoice',   lang);
      const { data } = await axios.post(`${API_BASE_URL}/process-command-unified/`, fd, {
        headers: { ...HEADERS, 'Content-Type': 'multipart/form-data' },
      });
      if (data?.reply) {
        addMsg({ role: 'assistant', text: data.reply, command: data.command, value: data.openEndedValue });
        speak(data.reply);
      }
    } catch (err) {
      const m = err.response?.data?.reply || err.message || 'Something went wrong.';
      setError(m);
      addMsg({ role: 'error', text: m });
    } finally { setLoading(false); }
  };

  const startRec = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
        .catch(() => navigator.mediaDevices.getUserMedia({ audio: true }));

      const fmt = ['audio/webm;codecs=opus','audio/webm','audio/mp4','audio/ogg','audio/wav']
        .find(f => MediaRecorder.isTypeSupported(f)) || 'audio/webm';

      chunksRef.current = [];
      recRef.current = new MediaRecorder(stream, { mimeType: fmt });

      let idx = 0, silence = 0, done = false;

      recRef.current.ondataavailable = async (e) => {
        if (!e.data.size) return;
        chunksRef.current.push(e.data);
        if (!done && idx > 0) {
          try {
            const fd = new FormData();
            fd.append('session_id',       session);
            fd.append('audio_chunk',      e.data);
            fd.append('chunk_index',      idx.toString());
            fd.append('silence_threshold','1000');
            const { data } = await axios.post(`${API_BASE_URL}/voice/stream-audio-chunk`, fd, {
              headers: { ...HEADERS, 'Content-Type': 'multipart/form-data' }, timeout: 2000,
            });
            silence = (data.is_silence || data.volume < 1000) ? silence + 1 : 0;
            if (silence >= 2 && idx >= 3) { done = true; stopRec(); }
          } catch (_) {}
        }
        idx++;
      };

      recRef.current.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(chunksRef.current, { type: fmt });
        await sendAudio(blob, fmt);
      };

      recRef.current.start(1000);
      setRecording(true);
      setRecTime(0);
      setError('');
      timerRef.current = setInterval(() => setRecTime(t => t + 1), 1000);
    } catch (err) {
      setError(
        err.name === 'NotAllowedError' ? 'Microphone access denied.' :
        err.name === 'NotFoundError'   ? 'No microphone found.'      : 'Microphone error.'
      );
    }
  };

  const stopRec = () => {
    if (recRef.current?.state === 'recording') recRef.current.stop();
    setRecording(false);
    clearInterval(timerRef.current);
  };

  const sendAudio = async (blob, fmt) => {
    setLoading(true);
    setError('');
    try {
      const ext = fmt.includes('mp4') ? 'mp4' : fmt.includes('ogg') ? 'ogg' : fmt.includes('wav') ? 'wav' : 'webm';
      const fd  = new FormData();
      fd.append('audio_file', blob, `rec.${ext}`);
      fd.append('session_id', session);
      fd.append('langChoice', lang);
      const { data } = await axios.post(`${API_BASE_URL}/process-command-unified/`, fd, {
        headers: { ...HEADERS, 'Content-Type': 'multipart/form-data' }, timeout: 30000,
      });
      if (data.transcribed_text) addMsg({ role: 'user', text: data.transcribed_text });
      if (data.reply) {
        addMsg({ role: 'assistant', text: data.reply, command: data.command, value: data.openEndedValue });
        speak(data.reply);
      }
    } catch (err) {
      const m = err.response?.data?.reply || err.message || 'Audio processing failed.';
      setError(m);
    } finally { setLoading(false); setRecTime(0); }
  };

  return (
    <div className="app-shell">

      {/* Nav */}
      <nav className="top-nav">
        <div className="nav-brand">
          <div className="nav-logo">{Icons.logo}</div>
          <span className="nav-title">Service Center</span>
        </div>
        <div className="nav-tabs">
          {[
            { id: 'chat',         label: 'Chat',         icon: Icons.chat     },
            { id: 'appointments', label: 'Appointments', icon: Icons.calendar },
          ].map(t => (
            <button key={t.id} className={`nav-tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
              <span className="tab-icon">{t.icon}</span>{t.label}
            </button>
          ))}
        </div>
      </nav>

      <main className="main-content">

        {/* Chat */}
        {tab === 'chat' && (
          <div className="chat-page">
            <div className="chat-card">

              {/* Header */}
              <div className="chat-header">
                <div className="chat-header-info">
                  <div className="assistant-avatar">{Icons.bot}</div>
                  <div>
                    <div className="assistant-name">AI Assistant</div>
                    <div className="assistant-status"><span className="status-dot" />Online</div>
                  </div>
                </div>
                <div className="chat-controls">
                  <div className="lang-toggle">
                    <button className={`lang-btn ${lang === 'en' ? 'active' : ''}`} onClick={() => setLang('en')}>EN</button>
                    <button className={`lang-btn ${lang === 'th' ? 'active' : ''}`} onClick={() => setLang('th')}>TH</button>
                  </div>
                  <button className="reset-btn" onClick={reset}>Reset</button>
                </div>
              </div>

              {/* Messages */}
              <div className="messages-window">
                {msgs.length === 0 && !loading && (
                  <div className="empty-state">
                    <div className="empty-icon">{Icons.chat}</div>
                    <div className="empty-text">Start a conversation</div>
                    <div className="empty-hint">Ask about your car, schedule service, or give a voice command.</div>
                  </div>
                )}

                {msgs.map((m, i) => (
                  <div key={i} className={`msg-row ${m.role === 'user' ? 'user' : m.role === 'error' ? 'error' : 'assistant'}`}>
                    <div className="msg-avatar">
                      {m.role === 'user' ? Icons.user : Icons.bot}
                    </div>
                    <div className="msg-body">
                      <div className="msg-bubble">
                        {m.text}
                        {m.role === 'assistant' && (m.command || m.value != null) && (
                          <div className="cmd-details">
                            {m.command && <span className="cmd-tag">{m.command}</span>}
                            {m.value != null && <span className="cmd-tag">val: {m.value}</span>}
                          </div>
                        )}
                      </div>
                      <span className="msg-time">{fmt(m.time)}</span>
                    </div>
                  </div>
                ))}

                {loading && (
                  <div className="typing-row">
                    <div className="msg-avatar">{Icons.bot}</div>
                    <div className="typing-bubble">
                      <div className="typing-dot"/><div className="typing-dot"/><div className="typing-dot"/>
                    </div>
                  </div>
                )}
                <div ref={bottomRef} />
              </div>

              {error && <div className="error-banner">{error}</div>}

              {/* Input */}
              <div className="input-bar">
                <input
                  className="text-input"
                  type="text"
                  value={text}
                  onChange={e => setText(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(e); }}}
                  placeholder={recording ? `Recording  ${recTime}s…` : 'Send a message…'}
                  disabled={loading || recording}
                />
                <button
                  className={`icon-btn ${recording ? 'recording' : ''}`}
                  onClick={recording ? stopRec : startRec}
                  disabled={loading || !micOk}
                  title={!micOk ? 'Microphone unavailable' : recording ? 'Stop' : 'Record'}
                >
                  {recording ? Icons.stop : Icons.mic}
                  {recording && <span className="rec-timer">{recTime}s</span>}
                </button>
                <button
                  className="icon-btn primary"
                  onClick={send}
                  disabled={loading || recording || !text.trim()}
                  title="Send"
                >
                  {Icons.send}
                </button>
              </div>

              {/* Footer */}
              <div className="session-bar">
                <span className="session-id-text">{session.slice(-14)}</span>
                <span>{msgs.length} msg{msgs.length !== 1 ? 's' : ''} · {lang === 'en' ? 'English' : 'Thai'}</span>
              </div>

            </div>
          </div>
        )}

        {/* Appointments */}
        {tab === 'appointments' && (
          <div className="appointments-page">
            <AppointmentDashboard />
          </div>
        )}

      </main>
    </div>
  );
}
