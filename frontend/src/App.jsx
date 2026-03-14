import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import './App.css';
import AppointmentDashboard from './components/AppointmentDashboard';

// --- Configuration ---
// const API_BASE_URL = '/api'; // Your FastAPI backend URL
const API_BASE_URL = 'http://localhost:8000';

function App() {
  const [activeTab, setActiveTab] = useState('chat');
  const [commandText, setCommandText] = useState('');
  const [apiResponse, setApiResponse] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  // For Audio Recording with MediaRecorder API
  const [isRecording, setIsRecording] = useState(false);
  const [isAudioSupported, setIsAudioSupported] = useState(false);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const [recordingTime, setRecordingTime] = useState(0);
  const recordingTimerRef = useRef(null);

  // --- NEW: State for Hugging Face Interaction ---
  const [hfPrompt, setHfPrompt] = useState('');
  const [hfResponse, setHfResponse] = useState('');
  const [isHfLoading, setIsHfLoading] = useState(false);
  const [hfError, setHfError] = useState('');

  const [sessionId, setSessionId] = useState(null);
  const [chatHistory, setChatHistory] = useState([]);
  const [isConversationActive, setIsConversationActive] = useState(false);
  const timeoutRef = useRef(null);
  const [conversationTimeout, setConversationTimeout] = useState(50);
  const [langChoice, setLangChoice] = useState("en");
  
  useEffect(() => {
    if (!sessionId) {
      const newSessionId = 'session-' + Date.now() + '-' + Math.random().toString(36).substring(2, 11);
      setSessionId(newSessionId);
      console.log('Generated new session ID:', newSessionId);
    }
  }, [sessionId]);

  const resetChat = async () => {
    console.log('Resetting conversation due to inactivity or manual reset');
    
    // Reset conversation on backend if session exists
    if (sessionId) {
      try {
        await axios.post(`${API_BASE_URL}/reset-conversation/${sessionId}`, {}, {
          headers: {
            'X-API-Key': 'nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM',
            'Content-Type': 'application/json'
          }
        });
        console.log('Backend conversation reset successfully');
      } catch (error) {
        console.error('Error resetting backend conversation:', error);
      }
    }
    
    // Reset frontend state
    setChatHistory([]);
    setIsConversationActive(false);
    setCommandText('');
    setApiResponse(null);
    setError('');
    
    // Generate new session ID
    const newSessionId = 'session-' + Date.now() + '-' + Math.random().toString(36).substring(2, 11);
    setSessionId(newSessionId);
    console.log('Generated new session ID after reset:', newSessionId);
    
    // Clear any existing timeout
    clearTimeout(timeoutRef.current);
  };

  const resetTimeout = () => {
    clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => {
      alert(`Resetting conversation due to ${conversationTimeout} seconds of inactivity.`);
      resetChat();
    }, conversationTimeout * 1000);
  };

  // Reset timeout when chat history changes or conversation becomes active
  useEffect(() => {
    if (isConversationActive && chatHistory.length > 0) {
      resetTimeout();
    }
    return () => clearTimeout(timeoutRef.current);
  }, [chatHistory, isConversationActive, conversationTimeout]);

  // Load conversation history when session ID changes
  useEffect(() => {
    if (sessionId && isConversationActive) {
      loadConversationHistory();
    }
  }, [sessionId]);

  const loadConversationHistory = async () => {
    if (!sessionId) return;
    
    try {
      const response = await axios.get(`${API_BASE_URL}/conversation-history/${sessionId}`, {
        headers: {
          'X-API-Key': 'nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM',
          'Content-Type': 'application/json'
        }
      });
      const history = response.data.chat_history;
      
      // Convert backend format to frontend format
      const frontendHistory = history.map(msg => ({
        sender: msg.role === 'user' ? 'user' : 'assistant',
        message: msg.content,
      }));
      
      setChatHistory(frontendHistory);
      console.log('Loaded conversation history:', frontendHistory);
    } catch (error) {
      if (error.response?.status === 404) {
        console.log('No existing conversation found for session:', sessionId);
        setChatHistory([]);
      } else {
        console.error('Error loading conversation history:', error);
      }
    }
  };

  useEffect(() => {
    // Simple browser-based audio support detection
    const checkAudioSupport = () => {
      console.log('🎙️ Checking browser audio support...');
      console.log('Browser:', navigator.userAgent);
      console.log('Protocol:', window.location.protocol);

      // Basic API checks
      const hasMediaDevices = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
      const hasMediaRecorder = !!window.MediaRecorder;

      if (!hasMediaDevices) {
        console.warn('❌ getUserMedia not supported');
        setIsAudioSupported(false);
        return;
      }

      if (!hasMediaRecorder) {
        console.warn('❌ MediaRecorder not supported');
        setIsAudioSupported(false);
        return;
      }

      // Check for at least one supported audio format
      const commonFormats = ['audio/webm', 'audio/mp4', 'audio/ogg', 'audio/wav'];
      const supportedFormat = commonFormats.find(format => MediaRecorder.isTypeSupported(format));

      if (!supportedFormat) {
        console.warn('❌ No supported audio formats');
        setIsAudioSupported(false);
        return;
      }

      console.log('✅ Browser supports audio recording');
      console.log('📱 Supported format:', supportedFormat);
      setIsAudioSupported(true);
    };

    checkAudioSupport();
  }, []);

  // Cleanup function to stop recording when component unmounts
  useEffect(() => {
    return () => {
      if (isRecording && mediaRecorderRef.current) {
        mediaRecorderRef.current.stop();
      }
      if (recordingTimerRef.current) {
        clearInterval(recordingTimerRef.current);
      }
    };
  }, [isRecording]);

  const handleInputChange = (event) => {
    setCommandText(event.target.value);
  };

  const handleHfInputChange = (event) => {
    setHfPrompt(event.target.value);
  };

  const speakText = (textToSpeak) => {
  if (!textToSpeak) return;
  
  return new Promise((resolve) => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(textToSpeak);

      // Set language based on current language choice
      utterance.lang = langChoice === 'th' ? 'th-TH' : 'en-US';

      // Get available voices and filter by language
      const voices = window.speechSynthesis.getVoices();
      
      let selectedVoice = null;
      if (langChoice === 'th') {
        // Try to find a Thai voice
        selectedVoice = voices.find(v => 
          v.lang.toLowerCase().includes('th') || 
          v.name.toLowerCase().includes('thai')
        );
        console.log('Looking for Thai voice, found:', selectedVoice?.name || 'none');
      } else {
        // Try to find an English voice
        selectedVoice = voices.find(v => 
          v.lang.toLowerCase().startsWith('en') || 
          v.name.toLowerCase().includes('english')
        );
        console.log('Looking for English voice, found:', selectedVoice?.name || 'none');
      }

      if (selectedVoice) {
        utterance.voice = selectedVoice;
        console.log(`Using voice: ${selectedVoice.name} (${selectedVoice.lang})`);
      } else {
        console.warn(`No ${langChoice === 'th' ? 'Thai' : 'English'} voice found, using default`);
      }

      utterance.rate = 0.9; 
      utterance.pitch = 1.0;

      utterance.onend = () => {
        console.log('Speech synthesis completed');
        resolve();
      };

      utterance.onerror = (event) => {
        console.error('Speech synthesis error:', event);
        resolve(); // Still resolve to continue the flow
      };

      window.speechSynthesis.speak(utterance);
    } else {
      console.warn('Speech Synthesis API not supported in this browser.');
      setError('Text-to-speech is not supported in your browser.');
      resolve();
    }
  });
};

  const handleSubmit = async (event, textToSubmit) => {
    if (event) event.preventDefault();
    
    const finalCommandText = textToSubmit !== undefined ? textToSubmit : commandText;
    if (!finalCommandText.trim()) {
      setError('Please enter or speak a command.');
      return;
    }

    setIsLoading(true);
    setError('');
    setApiResponse(null);
    setIsConversationActive(true);
    resetTimeout();

    // Append user message to chat immediately for better UX
    const userMessage = { 
      sender: 'user', 
      message: finalCommandText, 
    };
    setChatHistory(prev => [...prev, userMessage]);

    try {
      const formData = new FormData();
      formData.append('command_text', finalCommandText);
      formData.append('session_id', sessionId);
      formData.append('langChoice', langChoice);

      console.log('Sending request with session ID:', sessionId);

      const response = await axios.post(`${API_BASE_URL}/process-command-unified/`, formData, {
        headers: {
          'X-API-Key': 'nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM',
          'Content-Type': 'multipart/form-data'
        }
      });
      setApiResponse(response.data);

      // Update session ID if backend provides a new one
      if (response.data?.session_id && response.data.session_id !== sessionId) {
        setSessionId(response.data.session_id);
        console.log('Updated session ID from backend:', response.data.session_id);
      }

      if (response.data?.reply) {
        const { command, reply, openEndedValue } = response.data;

        const assistantMessage = { 
          sender: 'assistant',
          message: {
            command,
            reply,
            openEndedValue,
          },
        };

        setChatHistory(prev => [...prev, assistantMessage]);

        await speakText(reply);
      }
    } catch (err) {
      console.error('API Error (Gemini):', err);
      const errorMessage = err.response?.data?.reply || err.message;
      setError(`API Error: ${errorMessage}`);
      if (err.response?.data) {
        setApiResponse(err.response.data);
      }
      
      // Add error message to chat history
      const errorChatMessage = { 
        sender: 'assistant', 
        message: `Error: ${errorMessage}`,
      };
      setChatHistory(prev => [...prev, errorChatMessage]);
    } finally {
      setIsLoading(false);
      if (textToSubmit === undefined) setCommandText('');
    }
  };

  // Handler for Hugging Face prompt submission
  const handleHfSubmit = async (event) => {
    if (event) event.preventDefault();
    if (!hfPrompt.trim()) {
      setHfError('Please enter a prompt for the Hugging Face model.');
      return;
    }
    setIsHfLoading(true);
    setHfError('');
    setHfResponse('');

    try {
      const response = await axios.post(`${API_BASE_URL}/generate-hf-text/`, {
        prompt_text: hfPrompt,
        max_length: 150, // You can make this configurable
      }, {
        headers: {
          'X-API-Key': 'nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM',
          'Content-Type': 'application/json'
        }
      });
      setHfResponse(response.data.generated_text);
      // Optionally speak the HF response too
      // speakText(response.data.generated_text);
    } catch (err) {
      console.error('API Error (Hugging Face):', err);
      const errorMessage = err.response?.data?.error || err.response?.data?.detail || err.message || 'An unknown error occurred.';
      setHfError(`HF API Error: ${errorMessage}`);
    } finally {
      setIsHfLoading(false);
      // setHfPrompt(''); // Optionally clear prompt after submission
    }
  };



  const startRecording = async () => {
    if (!isAudioSupported) {
      setError('Audio recording is not supported in this browser.');
      return;
    }

    try {
      console.log('🎙️ Requesting microphone access...');

      // Start with basic audio constraints that work across all browsers/devices
      let stream;
      try {
        // Try with enhanced constraints first
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true
          }
        });
        console.log('✅ Got microphone access with enhanced settings');
      } catch (enhancedError) {
        console.log('⚠️ Enhanced settings failed, trying basic audio...');
        // Fallback to basic audio if enhanced fails
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        console.log('✅ Got microphone access with basic settings');
      }

      // Find the best supported audio format for this browser
      const audioFormats = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/mp4',
        'audio/ogg;codecs=opus',
        'audio/wav'
      ];

      let selectedFormat = 'audio/webm'; // Safe default
      for (const format of audioFormats) {
        if (MediaRecorder.isTypeSupported(format)) {
          selectedFormat = format;
          console.log('📱 Using audio format:', format);
          break;
        }
      }

      // Set up MediaRecorder
      audioChunksRef.current = [];
      mediaRecorderRef.current = new MediaRecorder(stream, {
        mimeType: selectedFormat
      });

      // Real-time VAD analysis variables
      let chunkIndex = 0;
      let silenceDetectionActive = true;
      let consecutiveSilenceChunks = 0;
      const SILENCE_CHUNKS_THRESHOLD = 2; // 2 seconds of silence to trigger auto-stop

      mediaRecorderRef.current.ondataavailable = async (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);

          // Perform real-time VAD analysis
          if (silenceDetectionActive) { // Analyze all chunks including first one
            try {
              const formData = new FormData();
              formData.append('session_id', sessionId);
              formData.append('audio_chunk', event.data);
              formData.append('chunk_index', chunkIndex.toString());
              formData.append('silence_threshold', '1000'); // Higher threshold for real-time

              const response = await axios.post(`${API_BASE_URL}/voice/stream-audio-chunk`, formData, {
                headers: {
                  'X-API-Key': 'nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM',
                  'Content-Type': 'multipart/form-data'
                },
                timeout: 2000 // Quick timeout for real-time processing
              });

              const { auto_stop_suggested, volume, is_silence } = response.data;
              console.log(`🎙️ Chunk ${chunkIndex}: Volume=${volume}, Silence=${is_silence}, Auto-stop=${auto_stop_suggested}`);

              // Track consecutive silence chunks
              if (is_silence || volume < 1000) {
                consecutiveSilenceChunks++;
                console.log(`🔇 Silence detected: ${consecutiveSilenceChunks}/${SILENCE_CHUNKS_THRESHOLD} chunks`);
              } else {
                consecutiveSilenceChunks = 0; // Reset on speech
                console.log(`🗣️ Speech detected, resetting silence counter`);
              }

              // Auto-stop after consecutive silence
              if (consecutiveSilenceChunks >= SILENCE_CHUNKS_THRESHOLD && chunkIndex >= 3) {
                console.log('🛑 Auto-stop triggered: Extended silence detected');
                silenceDetectionActive = false;
                stopRecording('auto-stop');
                return;
              }

            } catch (error) {
              console.error('VAD chunk analysis error:', error);
              // Continue recording on VAD errors
            }
          }

          chunkIndex++;
        }
      };

      mediaRecorderRef.current.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, {
          type: mediaRecorderRef.current.mimeType
        });

        console.log('🎵 Audio recorded:', audioBlob.size, 'bytes');

        // Release microphone
        stream.getTracks().forEach(track => track.stop());

        // Send to backend
        await sendAudioToBackend(audioBlob);
      };

      mediaRecorderRef.current.onerror = (event) => {
        console.error('Recording error:', event.error);
        setError(`Recording failed: ${event.error.message}`);
      };

      // Start recording with 1-second chunks for real-time VAD analysis
      mediaRecorderRef.current.start(1000); // 1000ms chunks
      setIsRecording(true);
      setRecordingTime(0);
      setError('');
      setCommandText('');
      console.log('🎙️ Recording started with real-time VAD analysis');
      setApiResponse(null);

      // Start timer
      recordingTimerRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);

      console.log('🔴 Recording started successfully');

    } catch (error) {
      console.error('❌ Microphone access failed:', error);

      let errorMessage = 'Could not access microphone. ';
      if (error.name === 'NotAllowedError') {
        errorMessage += 'Please allow microphone permissions and try again.';
      } else if (error.name === 'NotFoundError') {
        errorMessage += 'No microphone detected. Please connect a microphone.';
      } else {
        errorMessage += 'Please check your microphone and browser settings.';
      }

      setError(errorMessage);
    }
  };

  const stopRecording = (reason = 'manual') => {
    if (mediaRecorderRef.current && (isRecording || mediaRecorderRef.current.state === 'recording')) {
      console.log(`⏹️ Stopping recording (${reason})`);
      mediaRecorderRef.current.stop();
      setIsRecording(false);

      // Clear recording timer
      if (recordingTimerRef.current) {
        clearInterval(recordingTimerRef.current);
        recordingTimerRef.current = null;
      }

      // Update UI based on stop reason
      if (reason === 'auto-stop') {
        setCommandText('🛑 Auto-stopped - Processing audio...');
        console.log('🛑 Recording auto-stopped due to silence detection');
      } else {
        console.log('⏹️ Recording stopped manually');
      }
    } else {
      console.log('⚠️ Cannot stop recording - not currently recording');
    }
  };

  const sendAudioToBackend = async (audioBlob) => {
    setIsLoading(true);
    setIsConversationActive(true);
    resetTimeout();

    try {
      // Determine appropriate file extension based on MIME type
      let fileName = 'recording.webm'; // Default
      if (audioBlob.type.includes('opus')) {
        fileName = 'recording.opus';
      } else if (audioBlob.type.includes('ogg')) {
        fileName = 'recording.ogg';
      } else if (audioBlob.type.includes('mp4')) {
        fileName = 'recording.mp4';
      } else if (audioBlob.type.includes('wav')) {
        fileName = 'recording.wav';
      }

      const formData = new FormData();
      formData.append('audio_file', audioBlob, fileName);
      formData.append('session_id', sessionId);
      formData.append('langChoice', langChoice);

      // Enable auto-stop detection
      formData.append('enable_auto_stop', 'true');
      formData.append('silence_threshold', '500');
      formData.append('min_speech_duration_ms', '500');
      formData.append('silence_duration_ms', '1500');

      console.log('📤 Sending audio to backend for transcription...');
      console.log('Audio details:', {
        size: audioBlob.size,
        type: audioBlob.type,
        fileName: fileName
      });

      // Check if this was an auto-stopped recording
      const wasAutoStopped = commandText.includes('Auto-stopped');
      if (wasAutoStopped) {
        console.log('🛑 Processing auto-stopped recording');
        setCommandText('🛑 Auto-stopped - Transcribing audio...');
      }

      const response = await axios.post(`${API_BASE_URL}/process-command-unified/`, formData, {
        headers: {
          'X-API-Key': 'nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM',
          'Content-Type': 'multipart/form-data'
        },
        timeout: 30000, // 30 second timeout for Ubuntu systems
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          console.log(`Upload progress: ${percentCompleted}%`);
        }
      });

      const { transcribed_text, reply, command, openEndedValue, detected_language, auto_stop_detected, vad_info } = response.data;

      console.log('Audio transcribed:', transcribed_text);
      console.log('Detected language:', detected_language);

      // Log VAD information
      if (auto_stop_detected) {
        console.log('🛑 Auto-stop detected by VAD system');
      }
      if (vad_info) {
        console.log('🎙️ VAD Info:', vad_info);
      }

      // Add user message (transcribed text) to chat
      const userMessage = {
        sender: 'user',
        message: transcribed_text,
      };
      setChatHistory(prev => [...prev, userMessage]);

      // Set the transcribed text in the input field
      setCommandText(transcribed_text);
      setApiResponse(response.data);

      // Add assistant response to chat
      if (reply) {
        const assistantMessage = {
          sender: 'assistant',
          message: {
            command,
            reply,
            openEndedValue,
          },
        };
        setChatHistory(prev => [...prev, assistantMessage]);

        // Speak the response
        await speakText(reply);
      }

    } catch (error) {
      console.error('Error transcribing audio:', error);
      const errorMessage = error.response?.data?.reply || error.response?.data?.error || error.message;
      setError(`Audio transcription error: ${errorMessage}`);

      // Add error message to chat history
      const errorChatMessage = {
        sender: 'assistant',
        message: `Error: ${errorMessage}`,
      };
      setChatHistory(prev => [...prev, errorChatMessage]);
    } finally {
      setIsLoading(false);
      setRecordingTime(0);
    }
  };

  const handleAudioInput = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  return (
    <div className="container">
      <h1>Virtual Car Assistant</h1>

      {/* Tab Bar */}
      <div style={{ display: 'flex', borderBottom: '2px solid #ddd', marginBottom: '24px', gap: '4px' }}>
        {['chat', 'appointments'].map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '10px 24px',
              fontSize: '14px',
              fontWeight: '600',
              border: 'none',
              borderBottom: activeTab === tab ? '3px solid #2c3e50' : '3px solid transparent',
              backgroundColor: 'transparent',
              color: activeTab === tab ? '#2c3e50' : '#888',
              cursor: 'pointer',
              textTransform: 'capitalize',
              transition: 'color 0.2s',
            }}
          >
            {tab === 'chat' ? 'Chat' : 'Appointments'}
          </button>
        ))}
      </div>

      {activeTab === 'appointments' && <AppointmentDashboard />}

      {activeTab === 'chat' && <>
      <p className="car-description">
        Interact with your virtual car using voice or text commands!
        Try "turn on the AC", "play some music", or "navigate to downtown".
      </p>
      <img 
        src="/car-image.jpg" 
        alt="Car Dashboard" 
        className="car-image" 
        onError={(e) => e.target.style.display='none'} 
      />

      {/* Session and Conversation Controls */}
      <div className="control-buttons">
        <label>
          Timeout (seconds): 
          <input 
            type="number" 
            value={conversationTimeout} 
            onChange={(e) => setConversationTimeout(Math.max(10, parseInt(e.target.value) || 60))}
            min="10"
            max="300"
            style={{width: '60px', marginLeft: '5px'}}
          />
        </label>
        
        {/* ADD THIS BUTTON HERE */}
        <button 
          onClick={resetChat}
          className="reset-button"
          style={{
            marginLeft: '10px',
            backgroundColor: '#ff4444',
            color: 'white',
            border: 'none',
            padding: '8px 16px',
            borderRadius: '4px',
            cursor: 'pointer'
          }}
          title="Reset conversation and start fresh"
        >
          🔄 Reset Conversation
        </button>
        
        <div style={{ marginBottom: "1rem", marginTop: "1rem" }}>
          <span style={{ marginRight: "1rem" }}>Current language: {langChoice === "en" ? "English" : "Thai"}</span>
          <button onClick={() => setLangChoice(langChoice === "en" ? "th" : "en")}>
            Switch to {langChoice === "en" ? "Thai" : "English"}
          </button>
        </div>
      </div>

      <h2>Car Command System (Gemini)</h2>
      <form onSubmit={handleSubmit} className="input-form">
        <div className="input-area">
          <input
            type="text"
            value={commandText}
            onChange={handleInputChange}
            placeholder="Type or speak your command..."
            disabled={isLoading || isRecording}
          />
          <button type="submit" disabled={isLoading || isRecording || !commandText.trim()}>
            {isLoading ? 'Processing...' : 'Send Command'}
          </button>
          <button
            type="button"
            onClick={handleAudioInput}
            className={`voice-button ${isRecording ? 'recording' : ''}`}
            disabled={isLoading || !isAudioSupported}
            title={!isAudioSupported ?
              "Microphone not available - check browser permissions" :
              (isRecording ? `Recording... ${recordingTime}s - Click to stop` : "Click to record voice command")}
          >
            {!isAudioSupported ?
              'Mic N/A 🔇' :
              (isRecording ? `Recording... ${recordingTime}s 🔴` : 'Record 🎙️')}
          </button>
        </div>
      </form>

      {error && <p className="error-message">{error}</p>}

      {chatHistory.length > 0 && (
        <div className="chat-window">
          <h3>Conversation History ({chatHistory.length} messages)</h3>
          <div className="chat-messages">
            {chatHistory.map((msg, idx) => (
              <div key={idx} className={`chat-message ${msg.sender}`}>
                <span className="message-bubble">
                  {typeof msg.message === 'string' ? (
                    msg.message
                  ) : (
                    <>
                      <strong>🧠 Command Code:</strong> {msg.message.command}<br />
                      <strong>💬 Response:</strong> {msg.message.reply}<br />
                      <strong>🔍 Open-ended Value:</strong> {msg.message.openEndedValue !== null && msg.message.openEndedValue !== undefined 
                        ? msg.message.openEndedValue 
                        : 'null'}<br />
                    </>
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {isLoading && (
        <p className="loading-message" style={{ marginTop: '1rem', fontStyle: 'italic', color: '#555' }}>
          ⏳ Waiting for Gemini response...
        </p>
      )}

      <hr style={{margin: "40px 0"}} />

      {/* Hugging Face Interaction Section */}
      <h2>General Text Generation (Hugging Face)</h2>
      <form onSubmit={handleHfSubmit} className="input-form">
        <div className="input-area">
          <input
            type="text"
            value={hfPrompt}
            onChange={handleHfInputChange}
            placeholder="Enter prompt for Hugging Face model..."
            disabled={isHfLoading}
          />
          <button type="submit" disabled={isHfLoading || !hfPrompt.trim()}>
            {isHfLoading ? 'Generating...' : 'Generate Text'}
          </button>
        </div>
      </form>

      {hfError && <p className="error-message">{hfError}</p>}
      {isHfLoading && !hfError && <p className="loading-message">Waiting for Hugging Face response...</p>}
      {hfResponse && (
        <div className="response-area">
          <h3>Hugging Face Model Response:</h3>
          <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{hfResponse}</pre>
        </div>
      )}
      </>}
    </div>
  );
}

export default App;