# Car Command AI API - Backend Documentation

---

## Features

### Core Capabilities

- **Multi-language Support**: English, Thai, and Japanese
- **Audio Transcription**: Groq Whisper API (whisper-large-v3-turbo)
- **Natural Language Processing**: Google Gemini 2.5 Flash
- **Semantic Search**: Car manual search using sentence transformers and FAISS
- **Real-time Information**: Weather, location, dealership finder
- **Conversation History**: Session-based conversation tracking

### Data Sources

- **Car Manual**: PDF-based manual with semantic search
- **Car Commands**: CSV database of vehicle commands
- **Car Specifications**: CSV database of vehicle specs
- **Dealerships**: CSV database with Thai and English names
- **Jokes**: CSV database with Thai and English jokes

---

## API Endpoints

### 1. Root Endpoint

**GET** `/`

Returns API information and available endpoints.

```bash
curl -X GET "https://carplatform.dedyn.io/api/"
```

**Response:**
```json
{
  "message": "Welcome to the Car Command AI API",
  "version": "1.0.0",
  "authentication": "API key required for all endpoints except this one",
  "endpoints": {
    "/process-command-unified/":"Process car commands (text or audio) (POST) - Requires API key",
    "/process-command/":"Process text commands (POST) - Requires API key",
    "/transcribe-audio/":"Transcribe audio to text only (POST) - Requires API key",
    "/conversation-history/{session_id}":"Get conversation history (GET) - Requires API key",
    "/reset-conversation/{session_id}":"Reset conversation history (POST) - Requires API key",
    "/session/timeout":"Get/Set session timeout (GET/POST) - Requires API key",
    "/transcription/info/":"Get transcription service info (GET) - Requires API key",
    "/auth/verify":"Verify API key (GET) - Requires API key"},
    "authentication_methods":["Header: X-API-Key: <your-api-key>","Header: Authorization: Bearer <your-api-key>"]
}
```

---

### 2. Process Command (Text Only)

**POST** `/process-command/`

Process text commands using Gemini AI.

```bash
curl -X POST "https://carplatform.dedyn.io/api/process-command/" \
  -H "X-API-Key: your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "command_text": "Turn on the air conditioning",
    "lat": 13.7563,
    "lng": 100.5018,
    "session_id": "user-session-123",
    "langChoice": "en"
  }'
```

**Response:**
```json
{
  "command": "00060005",
  "reply": "Auto air conditioner ON completed.",
  "openEndedValue": null
}
```

---

### 3. Process Command Unified (Text or Audio)

**POST** `/process-command-unified/`

**Primary endpoint** for processing both text and audio commands.

#### Text Command Example:

```bash
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "command_text=Turn on the air conditioning" \
  -F "langChoice=en" \
  -F "session_id=user-session-123"
```

#### Audio Command Examples:

**Audio with English Response:**
```bash
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "audio_file=@/path/to/audio.mp3" \
  -F "langChoice=en" \
  -F "session_id=user-session-123"
```

**Audio with Thai Response:**
```bash
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "audio_file=@/path/to/audio.mp3" \
  -F "langChoice=th" \
  -F "session_id=user-session-123"
```

**Note**: The audio transcription automatically detects the audio input language, while `langChoice` controls the response language.

#### Parameters:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `command_text` | string | No* | - | Text command (mutually exclusive with audio_file) |
| `audio_file` | file | No* | - | Audio file (mp3, wav, m4a, webm, ogg, flac, aac) |
| `lat` | float | No | Random Bangkok | User latitude |
| `lng` | float | No | Random Bangkok | User longitude |
| `session_id` | string | No | Auto-generated | Session identifier |
| `langChoice` | string | No | "en" | Language: "en" or "th" |

*Either `command_text` OR `audio_file` must be provided, but not both.

#### Error Responses:

**Missing Input:**
```json
{
  "error": "Missing input",
  "reply": "Please provide either command_text or audio_file."
}
```

**Multiple Inputs:**
```json
{
  "error": "Multiple inputs",
  "reply": "Please provide either command_text OR audio_file, not both."
}
```

**Transcription Service Unavailable:**
```json
{
  "error": "Groq client not available",
  "reply": "Audio transcription service is not available."
}
```

**Invalid File Type:**
```json
{
  "error": "Invalid file type",
  "reply": "Please upload an audio file (mp3, wav, webm, etc.)."
}
```

**No Speech Detected:**
```json
{
  "error": "No speech detected",
  "reply": "No speech was detected in the audio. Please try speaking more clearly."
}
```

---

### 4. Transcribe Audio

**POST** `/transcribe-audio/`

**Pure transcription endpoint** - Converts audio to text without processing as a command. Returns only the transcribed text and detected language.

```bash
curl -X POST "https://carplatform.dedyn.io/api/transcribe-audio/" \
  -H "X-API-Key: your-api-key-here" \
  -F "audio_file=@/path/to/audio.mp3"
```

**Parameters:**
- `audio_file`: Audio file (required) - Supports mp3, wav, m4a, webm, ogg, flac, aac

**Response:**
```json
{
  "transcribed_text": "Turn on the air conditioning please.",
  "detected_language": "en"
}
```

**Supported Languages:** 90+ languages automatically detected by Groq Whisper, including:
- English, Thai, Japanese, Chinese, Korean, Vietnamese
- Spanish, French, German, Italian, Portuguese, Russian
- Arabic, Hindi, and many more

**Use Cases:**
- Pure transcription without command processing
- Language detection for audio files
- Testing audio quality and transcription accuracy
- Frontend integration where you want to handle the transcribed text yourself

**Note:** If you want to process the transcribed text as a car command, use `/process-command-unified/` instead.

---

### 5. Transcription Service Info

**GET** `/transcription/info/`

Get information about the transcription service.

```bash
curl -X GET "https://carplatform.dedyn.io/api/transcription/info/" \
  -H "X-API-Key: your-api-key-here"
```

**Response:**
```json
{
  "service": "Groq Whisper API",
  "model": "whisper-large-v3-turbo",
  "client_initialized": true,
  "features": {
    "language_detection": "Automatic",
    "supported_formats": ["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm", "flac"],
    "max_file_size": "25 MB",
    "speed": "Cloud-based (extremely fast)",
    "accuracy": "Very High (Whisper Large V3 Turbo)"
  }
}
```

---

### 8. Session Timeout Management

**GET** `/session/timeout`

Get current session timeout configuration.

```bash
curl -X GET "https://carplatform.dedyn.io/api/session/timeout" \
  -H "X-API-Key: your-api-key-here"
```

**Response:**
```json
{
  "current_timeout_seconds": 1800,
  "message": "Current session timeout configuration"
}
```

**POST** `/session/timeout`

Set session timeout dynamically (10 seconds to 1 hour).

```bash
curl -X POST "https://carplatform.dedyn.io/api/session/timeout" \
  -H "X-API-Key: your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "timeout_seconds": 3600
  }'
```

**Response:**
```json
{
  "message": "Session timeout updated successfully",
  "previous_timeout_seconds": 1800,
  "new_timeout_seconds": 3600
}
```

---

### 9. Authentication

**GET** `/auth/verify`

Verify if API key is valid.

```bash
curl -X GET "https://carplatform.dedyn.io/api/auth/verify" \
  -H "X-API-Key: your-api-key-here"
```

**Response:**
```json
{
  "status": "success",
  "message": "API key is valid",
  "authenticated": true
}
```

---

### 10. Conversation History

**GET** `/conversation-history/{session_id}`

Retrieve conversation history for a session.

```bash
curl -X GET "https://carplatform.dedyn.io/api/conversation-history/user-session-123" \
  -H "X-API-Key: your-api-key-here"
```

**Response:**
```json
{
  "session_id": "user-session-123",
  "message_count": 5,
  "chat_history": [
    {
      "role": "user",
      "content": ["Turn on AC"],
      "timestamp": "2025-10-29T12:00:00"
    },
    {
      "role": "assistant",
      "content": ["Auto air conditioner ON completed."],
      "timestamp": "2025-10-29T12:01:00"
    }
  ],
  "created_at": "2025-10-29T12:00:00",
  "last_activity": "2025-10-29T12:01:00"
}
```

---

### 11. Reset Conversation

**POST** `/reset-conversation/{session_id}`

Clear conversation history for a session.

```bash
curl -X POST "https://carplatform.dedyn.io/api/reset-conversation/user-session-123" \
  -H "X-API-Key: your-api-key-here"
```

**Response:**
```json
{
  "message": "Conversation reset successfully",
  "session_id": "user-session-123"
}
```

---

## Request/Response Structures

### Language Choice (`langChoice`)

The API supports three languages:

| Value | Language | Response Language | TTS Language |
|-------|----------|-------------------|--------------|
| `en` | English | English | en-US |
| `th` | Thai | Thai | th-TH |

**Important:** The response language is determined by `langChoice`, **not** by the detected language of the input audio.

**Example:**
- Input: Thai audio
- `langChoice`: "en"
- Result: Response in English

---

### Session Management

Sessions are automatically created and managed:

- **Auto-creation**: If no `session_id` is provided, one is generated
- **Timeout**: Default 5 minutes (configurable via `/session/timeout`)
- **Cleanup**: Expired sessions are automatically cleaned up
- **Conversation History**: Maintained per session for context-aware responses

---

### Audio File Requirements

**Supported Formats:**
- MP3 (`.mp3`)
- WAV (`.wav`)
- M4A (`.m4a`)
- WebM (`.webm`)
- OGG (`.ogg`)
- FLAC (`.flac`)
- AAC (`.aac`)

**Limitations:**
- Maximum file size: 25 MB (Groq API limit)
- Recommended: Clear audio with minimal background noise
- Sample rate: Any (automatically handled by Groq)

---

### Dealership Data Structure

The API uses `dealerships.csv` with the following columns:

- `Dealer Name Thai`: Thai language dealer name
- `Dealer Name Eng`: English language dealer name
- `Latitude`: Dealer latitude
- `Longitude`: Dealer longitude

**Language-specific responses:**
- Thai (`langChoice=th`): Uses `Dealer Name Thai`
- English (`langChoice=en`): Uses `Dealer Name Eng`

---

## Authentication

### API Key Authentication

All endpoints (except `/`) require API key authentication.

**Header Format:**
```
X-API-Key: your-api-key-here
```

---

## Language Support

### Multi-language Processing

The API handles two languages with full support:

#### English (`en`)
- Transcription: Automatic detection
- Response: English
- TTS: Google TTS (en-US) (on frontend)
- Dealership names: English names

#### Thai (`th`)
- Transcription: Automatic detection
- Response: Thai
- TTS: Google TTS (th-TH) (on frontend)
- Dealership names: Thai names

### Language Detection

- **Audio Input**: Groq Whisper automatically detects language
- **Response Language**: Determined by `langChoice` parameter
- **Mixed Language**: Input can be in any language; response follows `langChoice`

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| 200 | Success | Command processed successfully |
| 400 | Bad Request | Missing input, invalid file type |
| 401 | Unauthorized | Invalid or missing API key |
| 500 | Internal Server Error | Transcription failed, AI processing error |
| 503 | Service Unavailable | Groq client not initialized, Gemini not loaded |

### Common Errors

#### 1. Missing API Key
```json
{
  "error": "UNAUTHORIZED",
  "message": "Valid API key required. Include 'X-API-Key' header or 'Authorization: Bearer <key>' header."
}
```

#### 2. Groq Client Not Available
```json
{
  "error": "Groq client not available"
}
```

#### 3. Invalid Audio File
```json
{
  "error": "Invalid file type. Please upload an audio file (mp3, wav, webm, etc.)."
}
```

#### 4. No Speech Detected
```json
{
  "error": "No speech detected in the audio"
}
```

#### 5. Gemini Model Not Loaded
```json
{
  "command": null,
  "reply": "AI service (Gemini) is not available.",
  "openEndedValue": null,
  "error": "GEMINI_MODEL_NOT_LOADED"
}
```

---

**Options:**
- `--workers 4`: Run with 4 worker processes
- No `--reload`: Stable production mode

---

## Testing

### Test Transcription Service

Test the Groq Whisper API with sample audio files (if available).

### cURL Examples

#### 1. Text Command (English)
```bash
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "command_text=Turn on the air conditioning" \
  -F "langChoice=en" \
  -F "session_id=test-session-1"
```

#### 2. Audio Command (Thai)
```bash
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "audio_file=@thai_ac.mp3" \
  -F "langChoice=th" \
  -F "session_id=test-session-1"
```

#### 3. Get Conversation History
```bash
curl -X GET "https://carplatform.dedyn.io/api/conversation-history/test-session-1" \
  -H "X-API-Key: your-api-key-here"
```

#### 4. Check Transcription Service
```bash
curl -X GET "https://carplatform.dedyn.io/api/transcription/info/" \
  -H "X-API-Key: your-api-key-here"
```

---

## Troubleshooting

### Issue: No Speech Detected

**Symptom:**
```json
{
  "error": "No speech detected",
  "reply": "No speech was detected in the audio."
}
```

**Solution:**
- Ensure audio file contains clear speech
- Check audio file is not corrupted
- Verify audio format is supported
- Increase recording volume

### Issue: Wrong Language Response

**Symptom:** Response is in wrong language

**Solution:**
- Verify `langChoice` parameter is set correctly
- Remember: Response language follows `langChoice`, not detected language
- Check frontend is sending correct `langChoice` value

---

## License

This API is part of the Car Panasonic project.

---

## Support

For issues or questions:
1. Check this README
2. Review error messages in server logs
3. Test with cURL examples

---

**Last Updated:** 2025-10-29
**Transcription Service:** Groq Whisper API (whisper-large-v3-turbo)