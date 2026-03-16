import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import './App.css';
import AppointmentDashboard from './components/AppointmentDashboard';

const API_BASE_URL  = 'http://localhost:8000';
const API_KEY       = 'nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM';
const HEADERS       = { 'X-API-Key': API_KEY };
const GREETING_TEXT = "Hello! I'm Sarah from ABC Car Service Center. How can I help you today?";

const fmt = (d) => d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const uid = () => 'session-' + Date.now() + '-' + Math.random().toString(36).slice(2, 9);

/* ─── SVG icons ──────────────────────────────────────────── */
const Icons = {
  logo: <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M3 12h3m12 0h3M12 3v3m0 12v3"/></svg>,
  bot:  <svg viewBox="0 0 24 24"><rect x="3" y="8" width="18" height="12" rx="3"/><path d="M8 8V6a4 4 0 018 0v2"/><circle cx="9" cy="14" r="1.2" fill="currentColor" stroke="none"/><circle cx="15" cy="14" r="1.2" fill="currentColor" stroke="none"/></svg>,
  user: <svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>,
  chat: <svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>,
  mic:  <svg viewBox="0 0 24 24"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0014 0M12 19v3M9 22h6"/></svg>,
  stop: <svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none"/></svg>,
  send: <svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>,
  calendar: <svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>,
  sun:  <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>,
  moon: <svg viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>,
};

/* ─── detect when Sarah is ASKING for a specific field ───── */
const detectField = (reply) => {
  const r = reply.toLowerCase();
  // Must be a question/request — don't trigger on mere mentions
  const isAsk = r.includes('?') || /\b(please|could you|may i|can i|would you)\b/.test(r);
  if (!isAsk) return null;
  if (/\b(your (full )?name|name please|what'?s? your name|may i (have|know) your name|could i (get|have) your name)\b/.test(r)) return 'name';
  if (/\b(your (phone|mobile|contact) number|phone number please|could i get your phone|your number please|contact number)\b/.test(r)) return 'phone';
  if (/\b(your email( address)?|email address please|could i (get|have) your email|and your email)\b/.test(r)) return 'email';
  return null;
};

/* ─── detect when Sarah has finished and is saying goodbye ── */
const detectConversationEnd = (reply) => {
  const r = reply.toLowerCase();
  return /\b(appointment is confirmed|booking is confirmed|see you (on|then|soon)|goodbye|have a great day|have a nice day|thank you for (calling|booking|choosing)|your appointment has been (booked|scheduled|confirmed))\b/.test(r);
};

/* ─── pick best female TTS voice ─────────────────────────── */
const pickVoice = (lang) => {
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;
  if (lang === 'th') return voices.find(v => v.lang.includes('th')) || null;
  const en = voices.filter(v => v.lang.startsWith('en'));
  return (
    en.find(v => /enhanced|premium|neural/i.test(v.name))    // neural quality first
    || en.find(v => v.name === 'Samantha')                    // macOS natural
    || en.find(v => v.name === 'Google UK English Female')    // Chrome natural
    || en.find(v => /female|woman/i.test(v.name))             // any labelled female
    || en.find(v => v.lang === 'en-GB')                       // British = less robotic
    || en.find(v => v.lang === 'en-US')
    || en[0]
  ) || null;
};

export default function App() {
  const [tab, setTab]     = useState('chat');
  const [mode, setMode]   = useState('voice');
  const [theme, setTheme] = useState('dark');
  const [lang, setLang]   = useState('en');
  const [session, setSession] = useState(uid);

  /* chat (text mode) */
  const [text, setText]     = useState('');
  const [msgs, setMsgs]     = useState([{ role: 'assistant', text: GREETING_TEXT, time: new Date() }]);
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState('');

  /* voice mode */
  const [convActive, setConvActive]       = useState(false);
  const [vMsgs, setVMsgs]                 = useState([]);
  const [vLoading, setVLoading]           = useState(false);
  const [vError, setVError]               = useState('');
  const [recording, setRecording]         = useState(false);
  const [sarahSpeaking, setSarahSpeaking] = useState(false);
  const [inputField, setInputField]       = useState(null);
  const [fieldVal, setFieldVal]           = useState('');

  const recRef        = useRef(null);   // SpeechRecognition instance
  const autoListenRef = useRef(false);
  const bottomVRef    = useRef(null);
  const bottomRef     = useRef(null);
  const endConvRef    = useRef(null);  // kept fresh so sendTextCore can call endConversation

  /* ── theme ── */
  useEffect(() => { document.documentElement.setAttribute('data-theme', theme); }, [theme]);

  /* ── scroll ── */
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs, loading]);
  useEffect(() => { bottomVRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [vMsgs, vLoading]);

  /* ── cleanup ── */
  useEffect(() => () => {
    autoListenRef.current = false;
    try { recRef.current?.abort(); } catch (_) {}
    window.speechSynthesis?.cancel();
  }, []);

  /* ────────────────────────────────────────────────────────
     TTS — picks best human-sounding female voice
  ──────────────────────────────────────────────────────── */
  const speakText = useCallback((txt) => new Promise((resolve) => {
    if (!txt || !('speechSynthesis' in window)) { resolve(); return; }
    window.speechSynthesis.cancel();
    setSarahSpeaking(true);

    const doSpeak = () => {
      const u    = new SpeechSynthesisUtterance(txt);
      u.lang     = lang === 'th' ? 'th-TH' : 'en-GB';
      u.rate     = 0.93;
      u.pitch    = 1.08;
      const v = pickVoice(lang);
      if (v) u.voice = v;
      u.onend  = () => { setSarahSpeaking(false); resolve(); };
      u.onerror = () => { setSarahSpeaking(false); resolve(); };
      window.speechSynthesis.speak(u);
    };

    const voices = window.speechSynthesis.getVoices();
    if (voices.length > 0) doSpeak();
    else { window.speechSynthesis.onvoiceschanged = () => { window.speechSynthesis.onvoiceschanged = null; doSpeak(); }; }
  }), [lang]);

  /* ────────────────────────────────────────────────────────
     Send text to backend, speak reply, restart listening
  ──────────────────────────────────────────────────────── */
  const sendTextCore = useCallback(async (text) => {
    if (!autoListenRef.current) return;
    setVLoading(true);
    try {
      const fd = new FormData();
      fd.append('command_text', text);
      fd.append('session_id', session);
      fd.append('langChoice', lang);
      const { data } = await axios.post(`${API_BASE_URL}/process-command-unified/`, fd, {
        headers: { ...HEADERS, 'Content-Type': 'multipart/form-data' }, timeout: 15000,
      });
      if (data.reply) {
        setVMsgs(p => [...p, { role: 'assistant', text: data.reply, time: new Date() }]);
        const field = detectField(data.reply);
        setInputField(field);
        await speakText(data.reply);
        if (detectConversationEnd(data.reply)) {
          setTimeout(() => endConvRef.current?.(), 1800);
        } else if (!field && autoListenRef.current) {
          startRecCore();
        }
      }
    } catch (err) {
      setVError(err.response?.data?.reply || err.message || 'Something went wrong.');
    } finally { setVLoading(false); }
  }, [session, lang, speakText]); // startRecCore added below via ref

  /* ────────────────────────────────────────────────────────
     Browser SpeechRecognition — real-time, zero upload latency
  ──────────────────────────────────────────────────────── */
  const startRecCore = useCallback(() => {
    if (!autoListenRef.current) return;

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      setVError('Speech recognition not supported in this browser. Use Chrome or Edge.');
      return;
    }

    const recognition      = new SR();
    recRef.current         = recognition;
    recognition.continuous     = false;
    recognition.interimResults = true;
    recognition.lang           = lang === 'th' ? 'th-TH' : 'en-US';
    recognition.maxAlternatives = 1;

    const pendingId    = '__pending__' + Date.now();
    let finalText      = '';
    let hasAddedBubble = false;

    recognition.onstart = () => {
      setRecording(true);
      setVError('');
    };

    recognition.onresult = (e) => {
      let interim = '';
      finalText = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalText += e.results[i][0].transcript;
        else                      interim   += e.results[i][0].transcript;
      }
      const display = finalText || interim;
      if (!display) return;
      if (!hasAddedBubble) {
        hasAddedBubble = true;
        setVMsgs(p => [...p, { role: 'user', text: display, pending: !finalText, id: pendingId, time: new Date() }]);
      } else {
        setVMsgs(p => p.map(m => m.id === pendingId ? { ...m, text: display, pending: !finalText } : m));
      }
    };

    recognition.onend = () => {
      setRecording(false);
      recRef.current = null;
      if (!autoListenRef.current) return;
      if (finalText.trim()) {
        // Lock in the bubble, then send
        setVMsgs(p => p.map(m => m.id === pendingId ? { ...m, text: finalText.trim(), pending: false } : m));
        sendTextCore(finalText.trim());
      } else {
        // Nothing heard — remove empty bubble, listen again
        setVMsgs(p => p.filter(m => m.id !== pendingId));
        if (autoListenRef.current) startRecCore();
      }
    };

    recognition.onerror = (e) => {
      setRecording(false);
      recRef.current = null;
      setVMsgs(p => p.filter(m => m.id !== pendingId));
      if (e.error === 'no-speech') {
        if (autoListenRef.current) startRecCore();
        return;
      }
      if (e.error !== 'aborted') setVError(`Mic error: ${e.error}`);
    };

    try { recognition.start(); } catch (_) {}
  }, [lang, sendTextCore]);

  /* ────────────────────────────────────────────────────────
     Submit typed field (name / phone / email)
  ──────────────────────────────────────────────────────── */
  const submitField = useCallback(async () => {
    const val = fieldVal.trim();
    if (!val || vLoading) return;
    setFieldVal('');
    setInputField(null);
    setVLoading(true);
    setVMsgs(p => [...p, { role: 'user', text: val, time: new Date() }]);
    try {
      const fd = new FormData();
      fd.append('command_text', val);
      fd.append('session_id', session);
      fd.append('langChoice', lang);
      const { data } = await axios.post(`${API_BASE_URL}/process-command-unified/`, fd, {
        headers: { ...HEADERS, 'Content-Type': 'multipart/form-data' },
      });
      if (data?.reply) {
        setVMsgs(p => [...p, { role: 'assistant', text: data.reply, time: new Date() }]);
        const field = detectField(data.reply);
        setInputField(field);
        await speakText(data.reply);
        if (detectConversationEnd(data.reply)) {
          setTimeout(() => endConvRef.current?.(), 1800);
        } else if (!field && autoListenRef.current) {
          startRecCore();
        }
      }
    } catch (err) {
      setVError(err.response?.data?.reply || err.message || 'Something went wrong.');
    } finally { setVLoading(false); }
  }, [fieldVal, vLoading, session, lang, speakText, startRecCore]);

  /* ────────────────────────────────────────────────────────
     Start / End conversation
  ──────────────────────────────────────────────────────── */
  const startConversation = useCallback(async () => {
    setConvActive(true);
    autoListenRef.current = true;
    setVMsgs([{ role: 'assistant', text: GREETING_TEXT, time: new Date() }]);
    setInputField(null);
    setFieldVal('');
    setVError('');
    await speakText(GREETING_TEXT);
    if (autoListenRef.current) startRecCore();
  }, [speakText, startRecCore]);

  const endConversation = useCallback(() => {
    autoListenRef.current = false;
    try { recRef.current?.abort(); } catch (_) {}
    recRef.current = null;
    window.speechSynthesis.cancel();
    setConvActive(false);
    setRecording(false);
    setSarahSpeaking(false);
    setInputField(null);
    setFieldVal('');
    setVMsgs([]);
    setVError('');
    try { axios.post(`${API_BASE_URL}/reset-conversation/${session}`, {}, { headers: HEADERS }); } catch (_) {}
    setSession(uid());
  }, [session]);

  // Keep ref fresh so sendTextCore / submitField can call it without stale closure
  endConvRef.current = endConversation;

  /* ────────────────────────────────────────────────────────
     Text mode helpers
  ──────────────────────────────────────────────────────── */
  const addMsg = (msg) => setMsgs(p => [...p, { ...msg, time: new Date() }]);

  const reset = async () => {
    try { await axios.post(`${API_BASE_URL}/reset-conversation/${session}`, {}, { headers: HEADERS }); } catch (_) {}
    setSession(uid());
    setMsgs([{ role: 'assistant', text: GREETING_TEXT, time: new Date() }]);
    setText(''); setError('');
  };

  const send = async (e, override) => {
    if (e) e.preventDefault();
    const t = override ?? text;
    if (!t.trim()) return;
    setText(''); setError(''); setLoading(true);
    addMsg({ role: 'user', text: t });
    try {
      const fd = new FormData();
      fd.append('command_text', t);
      fd.append('session_id', session);
      fd.append('langChoice', lang);
      const { data } = await axios.post(`${API_BASE_URL}/process-command-unified/`, fd, {
        headers: { ...HEADERS, 'Content-Type': 'multipart/form-data' },
      });
      if (data?.reply) addMsg({ role: 'assistant', text: data.reply });
    } catch (err) {
      const m = err.response?.data?.reply || err.message || 'Something went wrong.';
      setError(m); addMsg({ role: 'error', text: m });
    } finally { setLoading(false); }
  };

  /* ── status ── */
  const statusLabel = sarahSpeaking ? 'Speaking…'
    : recording  ? 'Listening…'
    : vLoading   ? 'Thinking…'
    : convActive ? 'Active'
    : 'ABC Service Center';

  const isOrbActive = sarahSpeaking || recording || vLoading;

  const fieldMeta = {
    name:  { placeholder: 'Type your full name…',     type: 'text',  label: 'Your Name' },
    phone: { placeholder: 'Type your phone number…',  type: 'tel',   label: 'Phone Number' },
    email: { placeholder: 'Type your email address…', type: 'email', label: 'Email Address' },
  };

  /* ═══════════════════════════════════════════════════════
     RENDER
  ═══════════════════════════════════════════════════════ */
  return (
    <div className="app-shell">

      {/* ── Nav ── */}
      <nav className="top-nav">
        <div className="nav-left">
          <div className="nav-logo">{Icons.logo}</div>
          <div className="nav-brand">
            <span className="nav-title">Service Center</span>
            <span className="nav-title-sub">AI Assistant</span>
          </div>
        </div>

        {tab === 'chat' && (
          <div className="mode-pill">
            <button className={`mode-btn ${mode === 'voice' ? 'active' : ''}`} onClick={() => setMode('voice')}>{Icons.mic} Voice</button>
            <button className={`mode-btn ${mode === 'text'  ? 'active' : ''}`} onClick={() => setMode('text')} >{Icons.chat} Text</button>
          </div>
        )}

        <div className="nav-right">
          {tab === 'chat' && (
            <>
              <div className="lang-toggle">
                <button className={`lang-btn ${lang === 'en' ? 'active' : ''}`} onClick={() => setLang('en')}>EN</button>
                <button className={`lang-btn ${lang === 'th' ? 'active' : ''}`} onClick={() => setLang('th')}>TH</button>
              </div>
              <div className="nav-divider" />
            </>
          )}
          <button className={`nav-icon-btn ${tab === 'appointments' ? 'active' : ''}`} onClick={() => setTab(tab === 'appointments' ? 'chat' : 'appointments')} title="Appointments">{Icons.calendar}</button>
          <button className="nav-icon-btn" onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')} title="Toggle theme">{theme === 'dark' ? Icons.sun : Icons.moon}</button>
        </div>
      </nav>

      <main className="main-content">

        {/* ══════════════════════════════════════
            VOICE MODE
        ══════════════════════════════════════ */}
        {tab === 'chat' && mode === 'voice' && (
          <div className="voice-card">

            <div className="sarah-identity">
              <div className={`sarah-orb ${isOrbActive ? 'active' : ''}`}>
                <div className="orb-ring r1" />
                <div className="orb-ring r2" />
                <div className="orb-ring r3" />
                <div className={`orb-core ${sarahSpeaking ? 'speaking' : recording ? 'recording' : ''}`}>
                  {recording ? Icons.mic : Icons.bot}
                </div>
              </div>
              <div className="sarah-info">
                <div className="sarah-name">Sarah</div>
                <div className="sarah-meta">
                  <span className={`status-dot ${convActive ? 'active' : ''}`} />
                  {statusLabel}
                </div>
              </div>
            </div>

            <div className={`waveform ${isOrbActive ? 'active' : ''}`}>
              {[...Array(13)].map((_, i) => <span key={i} className="wave-bar" style={{ '--i': i }} />)}
            </div>

            <div className="voice-log">
              {!convActive ? (
                <div className="vlog-idle">Press <strong>Start Conversation</strong> to begin</div>
              ) : (
                <>
                  {vMsgs.map((m, i) => (
                    <div key={i} className={`vlog-entry ${m.role}`}>
                      <div className="vlog-avatar">{m.role === 'user' ? Icons.user : Icons.bot}</div>
                      <div className="vlog-body">
                        <span className="vlog-label">{m.role === 'user' ? 'You' : 'Sarah'}</span>
                        <div className={`vlog-bubble${m.pending ? ' vlog-pending' : ''}`}>{m.text}</div>
                      </div>
                    </div>
                  ))}
                  {vLoading && (
                    <div className="vlog-entry assistant">
                      <div className="vlog-avatar">{Icons.bot}</div>
                      <div className="vlog-body">
                        <span className="vlog-label">Sarah</span>
                        <div className="vlog-bubble vlog-thinking">
                          <span className="thinking-dot"/><span className="thinking-dot"/><span className="thinking-dot"/>
                        </div>
                      </div>
                    </div>
                  )}
                  <div ref={bottomVRef} />
                </>
              )}
            </div>

            {inputField && convActive && (
              <div className="field-input-bar">
                <div className="field-label">{fieldMeta[inputField].label}</div>
                <div className="field-row">
                  <input
                    className="field-input"
                    type={fieldMeta[inputField].type}
                    placeholder={fieldMeta[inputField].placeholder}
                    value={fieldVal}
                    onChange={e => setFieldVal(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && submitField()}
                    autoFocus
                    disabled={vLoading}
                  />
                  <button className="field-send-btn" onClick={submitField} disabled={!fieldVal.trim() || vLoading}>
                    {Icons.send}
                  </button>
                </div>
              </div>
            )}

            {vError && <div className="voice-error">{vError}</div>}

            <div className="conv-btns">
              {!convActive ? (
                <button className="conv-btn start" onClick={startConversation} disabled={vLoading}>
                  {Icons.mic} Start Conversation
                </button>
              ) : (
                <button className="conv-btn end" onClick={endConversation}>
                  {Icons.stop} End Conversation
                </button>
              )}
            </div>

            <p className="voice-footer">Powered by Sarah · ABC Service Center</p>
          </div>
        )}

        {/* ══════════════════════════════════════
            TEXT MODE
        ══════════════════════════════════════ */}
        {tab === 'chat' && mode === 'text' && (
          <div className="chat-card">
            <div className="chat-header">
              <div className="chat-header-info">
                <div className="assistant-avatar">{Icons.bot}</div>
                <div>
                  <div className="assistant-name">Sarah</div>
                  <div className="assistant-status"><span className="status-dot" />Online</div>
                </div>
              </div>
              <button className="reset-btn" onClick={reset}>Reset</button>
            </div>

            <div className="messages-window">
              {msgs.length <= 1 && !loading && (
                <div className="empty-state">
                  <div className="empty-hint">Ask about services, book an appointment, or say hello.</div>
                </div>
              )}
              {msgs.map((m, i) => (
                <div key={i} className={`msg-row ${m.role === 'user' ? 'user' : m.role === 'error' ? 'error' : 'assistant'}`}>
                  <div className="msg-avatar">{m.role === 'user' ? Icons.user : Icons.bot}</div>
                  <div className="msg-body">
                    <div className="msg-bubble">{m.text}</div>
                    <span className="msg-time">{fmt(m.time)}</span>
                  </div>
                </div>
              ))}
              {loading && (
                <div className="typing-row">
                  <div className="msg-avatar">{Icons.bot}</div>
                  <div className="typing-bubble"><div className="typing-dot"/><div className="typing-dot"/><div className="typing-dot"/></div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {error && <div className="error-banner">{error}</div>}

            <div className="input-bar">
              <input
                className="text-input"
                type="text"
                value={text}
                onChange={e => setText(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(e); } }}
                placeholder="Send a message…"
                disabled={loading}
              />
              <button className="icon-btn primary" onClick={send} disabled={loading || !text.trim()}>{Icons.send}</button>
            </div>

            <div className="session-bar">
              <span className="session-id-text">{session.slice(-14)}</span>
              <span>{msgs.length} msg{msgs.length !== 1 ? 's' : ''} · {lang === 'en' ? 'English' : 'Thai'}</span>
            </div>
          </div>
        )}

        {tab === 'appointments' && (
          <div className="appointments-page"><AppointmentDashboard /></div>
        )}

      </main>
    </div>
  );
}
