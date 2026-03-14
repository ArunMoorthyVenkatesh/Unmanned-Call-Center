# Car LLM Agent API

A sophisticated car assistant API that processes both text and audio commands using Google Gemini AI and OpenAI Whisper for speech recognition.

**⚠️ IMPORTANT FOR DEVELOPERS:** Before deploying to EC2, always check `frontend/src/App.jsx` and ensure `const API_URL = "/api";` (not `localhost:8000`). 

## Features

- **Text Command Processing**: Send text commands directly to the car assistant
- **Audio Command Processing**: Upload audio files (MP3, WAV, WebM, etc.) for automatic transcription and processing
- **Unified Endpoint**: Single endpoint that automatically handles both text and audio inputs
- **Browser-Independent**: Audio recording works across all modern browsers
- **High-Quality Transcription**: Uses OpenAI Whisper "turbo" model for accurate speech-to-text
- **Conversation Memory**: Maintains conversation context across requests
- **Multi-language Support**: Supports English and Thai languages

## API Authentication

All endpoints require an API key for authentication. Include the API key in your requests using one of these methods:

```bash
# Method 1: X-API-Key header
-H "X-API-Key: your-api-key-here"

# Method 2: Authorization Bearer header
-H "Authorization: Bearer your-api-key-here"
```

## Endpoints

### 1. Unified Command Processing (Recommended)

**Endpoint**: `POST /process-command-unified/`

This is the main endpoint that automatically handles both text and audio inputs.

#### Text Command Example:
```bash
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "command_text=turn on the air conditioning" \
  -F "langChoice=en" \
  -F "session_id=my-session-123"
```

#### Audio Command Examples:

**Audio with English Response:**
```bash
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "audio_file=@/path/to/your/audio.mp3" \
  -F "langChoice=en" \
  -F "session_id=my-session-123"
```

**Audio with Thai Response:**
```bash
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "audio_file=@/path/to/your/audio.mp3" \
  -F "langChoice=th" \
  -F "session_id=my-session-123"
```

**Note**: The audio transcription automatically detects the input language (Thai, English, etc.), while `langChoice` controls the response language.

#### Parameters:
- `command_text` (string, optional): Text command to process
- `audio_file` (file, optional): Audio file to transcribe and process
- `lat` (float, optional): Latitude for location-based queries
- `lng` (float, optional): Longitude for location-based queries  
- `session_id` (string, optional): Session ID for conversation continuity
- `langChoice` (string, default: "en"): Response language ("en" for English response, "th" for Thai response)

**Note**: Provide either `command_text` OR `audio_file`, not both.

#### Response Format:
```json
{
  "command": "00000001",
  "reply": "Air conditioning turned on.",
  "openEndedValue": null,
  "input_type": "text",
  "transcribed_text": "turn on the air conditioning"
}
```

### 2. Text-Only Command Processing

**Endpoint**: `POST /process-command/`

For text-only command processing (legacy endpoint).

```bash
curl -X POST "https://carplatform.dedyn.io/api/process-command/" \
  -H "X-API-Key: your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "command_text": "play some music",
    "langChoice": "en",
    "session_id": "my-session-123"
  }'
```

### 3. Audio-Only Transcription

**Endpoint**: `POST /transcribe-audio/`

For audio-only transcription and processing (legacy endpoint). Ensure '@' symbol is used before the audio file path.

```bash
curl -X POST "https://carplatform.dedyn.io/api/transcribe-audio/" \
  -H "X-API-Key: your-api-key-here" \
  -F "audio_file=@/path/to/your/audio.mp3" \
  -F "langChoice=en" \
  -F "session_id=my-session-123"
```

### 4. Conversation History

**Endpoint**: `GET /conversation-history/{session_id}`

Retrieve conversation history for a specific session.

```bash
curl -X GET "https://carplatform.dedyn.io/api/conversation-history/my-session-123" \
  -H "X-API-Key: your-api-key-here"
```

### 5. Reset Conversation

**Endpoint**: `POST /reset-conversation/{session_id}`

Reset conversation history for a specific session.

```bash
curl -X POST "https://carplatform.dedyn.io/api/reset-conversation/my-session-123" \
  -H "X-API-Key: your-api-key-here"
```

### 6. API Information

**Endpoint**: `GET /`

Get API information and available endpoints (no authentication required).

```bash
curl -X GET "https://carplatform.dedyn.io/api/"
```

### 7. Session Timeout Management

**Get Current Timeout**: `GET /session/timeout`

Get the current session timeout configuration.

```bash
curl -X GET "https://carplatform.dedyn.io/api/session/timeout" \
  -H "X-API-Key: your-api-key-here"
```

**Set Session Timeout**: `POST /session/timeout`

Dynamically adjust the session timeout (10-3600 seconds).

```bash
curl -X POST "https://carplatform.dedyn.io/api/session/timeout" \
  -H "X-API-Key: your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{"timeout_seconds": 120}'
```

### 8. API Key Verification

**Endpoint**: `GET /auth/verify`

Verify if your API key is valid.

```bash
curl -X GET "https://carplatform.dedyn.io/api/auth/verify" \
  -H "X-API-Key: your-api-key-here"
```

## Supported Audio Formats

The API supports the following audio formats:
- MP3 (.mp3)
- WAV (.wav)
- WebM (.webm)
- M4A (.m4a)
- OGG (.ogg)
- FLAC (.flac)
- AAC (.aac)

## Example Car Commands

Here are some example commands:

### Climate Control
```bash
# Turn on AC
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "command_text=turn on the air conditioning"

# Set temperature
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "command_text=set temperature to 22 degrees"
```

### Entertainment
```bash
# Play music
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "command_text=play some music"

# Change to radio
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "command_text=switch to radio"
```

### Navigation
```bash
# Navigate to location
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "command_text=navigate to downtown Bangkok"
```

## Installation and Setup

### Backend Setup

1. Install dependencies:
```bash
cd backend
pip install -r requirements.txt
```

2. **Install FFmpeg (REQUIRED for audio processing):**
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y ffmpeg

# CentOS/RHEL
sudo yum install -y ffmpeg

# macOS
brew install ffmpeg
```

3. Set up environment variables in `.env`:
```
GEMINI_API_KEY=your_gemini_api_key
SERPAPI_API_KEY=your_serpapi_key
WEATHER_API_KEY=your_weather_api_key
```

3. Start the backend server:
```bash
python api_car.py
```

The server will start on `http://localhost:8000`

### Frontend Setup (Optional)

1. Install dependencies:
```bash
cd frontend
npm install
```

2. Start the development server:
```bash
npm run dev
```

The frontend will be available at `http://localhost:5173` or `http://localhost:5174`

## Error Handling

The API returns appropriate HTTP status codes and error messages:

- `400 Bad Request`: Invalid input or missing required parameters
- `401 Unauthorized`: Invalid or missing API key
- `503 Service Unavailable`: AI services not available
- `500 Internal Server Error`: Server-side processing errors

Example error response:
```json
{
  "error": "Invalid file type",
  "reply": "Please upload an audio file (mp3, wav, webm, etc.)."
}
```

## Response Format

All successful responses include:
- `command`: 8-digit command code for the car system
- `reply`: Natural language response from the assistant
- `openEndedValue`: Any extracted values from the command
- `input_type`: "text" or "audio" indicating input method
- `transcribed_text`: (audio only) The transcribed text from audio input

## Session Management

Use session IDs to maintain conversation context across multiple requests. The system will remember previous interactions within the same session, enabling more natural conversations.

## 🔄 Continuous Conversations with cURL

For users integrating via cURL, here's how to maintain conversation continuity like the frontend interface:

### **Key Concept: Session ID**

The backend uses `session_id` to maintain conversation context. Same session ID = continuous conversation.

### **🚀 Basic Continuous Conversation Pattern**

#### **1. Generate a Session ID**
```bash
# Create a unique session ID (use same ID for entire conversation)
SESSION_ID="car-conversation-$(date +%Y%m%d-%H%M%S)-$$"
echo "Using session ID: $SESSION_ID"
```

#### **2. First Command**
```bash
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "command_text=turn on the air conditioning" \
  -F "session_id=$SESSION_ID" \
  -F "langChoice=en"
```

#### **3. Follow-up Commands (Same Session)**
```bash
# The system remembers the AC was turned on
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "command_text=is the ac on?" \
  -F "session_id=$SESSION_ID" \
  -F "langChoice=en"

# Continue the conversation
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "command_text=set it to 22 degrees" \
  -F "session_id=$SESSION_ID" \
  -F "langChoice=en"
```

### **🎙️ Audio + Text Conversation**

```bash
# Mix audio and text in same conversation
SESSION_ID="mixed-conversation-$(date +%s)"

# Start with audio command
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "audio_file=@turn_on_ac.mp3" \
  -F "session_id=$SESSION_ID" \
  -F "langChoice=en"

# Follow up with text (remembers audio command)
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "command_text=what's the current temperature?" \
  -F "session_id=$SESSION_ID" \
  -F "langChoice=en"
```

### **📚 Session Management Commands**

#### **View Conversation History**
```bash
curl -X GET "https://carplatform.dedyn.io/api/conversation-history/$SESSION_ID" \
  -H "X-API-Key: your-api-key-here"
```

**Response:**
```json
{
  "session_id": "car-conversation-20250916-123456-1234",
  "chat_history": [
    {
      "role": "user",
      "content": "turn on the air conditioning",
      "timestamp": "2025-09-16T12:34:56.789Z"
    },
    {
      "role": "assistant",
      "content": "Air conditioning turned on.",
      "timestamp": "2025-09-16T12:34:57.123Z"
    }
  ],
  "created_at": "2025-09-16T12:34:56.000Z",
  "last_activity": "2025-09-16T12:34:57.123Z"
}
```

#### **Reset Conversation**
```bash
curl -X POST "https://carplatform.dedyn.io/api/reset-conversation/$SESSION_ID" \
  -H "X-API-Key: your-api-key-here"
```

### **🔧 Complete Conversation Script**

```bash
#!/bin/bash

# Configuration
API_KEY="your-api-key-here"
API_URL="https://carplatform.dedyn.io/api/process-command-unified/"
SESSION_ID="car-conversation-$(date +%Y%m%d-%H%M%S)-$$"

echo "🚗 Starting car conversation with session: $SESSION_ID"

# Sample function to send command and show response
send_command() {
    local command="$1"
    local type="$2"  # "text" or "audio"

    echo ""
    echo "👤 User: $command"

    if [ "$type" = "audio" ]; then
        response=$(curl -s -X POST "$API_URL" \
            -H "X-API-Key: $API_KEY" \
            -F "audio_file=@$command" \
            -F "session_id=$SESSION_ID" \
            -F "langChoice=en")
    else
        response=$(curl -s -X POST "$API_URL" \
            -H "X-API-Key: $API_KEY" \
            -F "command_text=$command" \
            -F "session_id=$SESSION_ID" \
            -F "langChoice=en")
    fi

    # Extract reply from JSON response
    reply=$(echo "$response" | jq -r '.reply // "No reply"')
    command_code=$(echo "$response" | jq -r '.command // "N/A"')

    echo "🤖 Assistant: $reply"
    echo "📟 Command Code: $command_code"
}

# Conversation flow
send_command "turn on the air conditioning" "text"
send_command "is the ac on?" "text"
send_command "set temperature to 22 degrees" "text"
send_command "what's the current temperature?" "text"

# View conversation history
echo ""
echo "📚 Conversation History:"
curl -s -X GET "https://carplatform.dedyn.io/api/conversation-history/$SESSION_ID" \
    -H "X-API-Key: $API_KEY" | jq '.chat_history'

echo ""
echo "✅ Conversation complete. Session ID: $SESSION_ID"
```

### **🎯 Session ID Best Practices**

#### **For Car Systems:**
```bash
# Use consistent daily session per car
SESSION_ID="car-$(hostname)-$(date +%Y%m%d)"

# Or per trip session
SESSION_ID="trip-$(date +%Y%m%d-%H%M%S)"

# Or per user session
SESSION_ID="user-john-$(date +%Y%m%d)"
```

#### **For Testing:**
```bash
# Unique session per test
SESSION_ID="test-$(date +%s)-$$"

# Named test sessions
SESSION_ID="climate-test-$(date +%Y%m%d)"
```

### **⏰ Session Timeout Configuration**

The system has two timeout mechanisms:

#### **Backend Session Timeout**
- **Default**: 50 seconds (configurable in backend)
- **Location**: `backend/api_car.py` line 72: `SESSION_TIMEOUT = timedelta(seconds=50)`
- **Purpose**: Automatically removes inactive sessions from server memory
- **Behavior**: Sessions expire after no API activity

**To modify backend timeout:**
```python
# In backend/api_car.py
SESSION_TIMEOUT = timedelta(seconds=120)  # Change to 2 minutes
```

#### **Frontend Auto-Reset Timeout (Web Interface)**
- **Default**: 50 seconds (adjustable in UI)
- **Range**: 10-300 seconds
- **Purpose**: Automatically resets conversation in browser after inactivity
- **User Control**: Adjustable via "Timeout (seconds)" input in web interface

**For cURL users**: The frontend timeout doesn't affect API usage - only the backend session timeout applies.

#### **Dynamic Timeout Configuration (API Endpoint)**

Users can adjust the session timeout dynamically via API endpoint:

**Get Current Timeout:**
```bash
curl -X GET "https://carplatform.dedyn.io/api/session/timeout" \
  -H "X-API-Key: your-api-key-here"
```

**Response:**
```json
{
  "current_timeout_seconds": 50,
  "message": "Current session timeout configuration"
}
```

**Set New Timeout:**
```bash
# Set timeout to 2 minutes (120 seconds)
curl -X POST "https://carplatform.dedyn.io/api/session/timeout" \
  -H "X-API-Key: your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{"timeout_seconds": 120}'

# Set timeout to 5 minutes for long conversations
curl -X POST "https://carplatform.dedyn.io/api/session/timeout" \
  -H "X-API-Key: your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{"timeout_seconds": 300}'
```

**Response:**
```json
{
  "message": "Session timeout updated successfully",
  "previous_timeout_seconds": 50,
  "new_timeout_seconds": 120
}
```

**Timeout Range:** 10 seconds (minimum) to 3600 seconds (1 hour maximum)

#### **Environment Variable Configuration (Alternative)**
You can also set the default timeout via environment variable:

```bash
# Set in .env file or environment
export SESSION_TIMEOUT_SECONDS=120

# Or when starting the server
SESSION_TIMEOUT_SECONDS=300 python api_car.py
```

#### **Timeout Behavior Examples**

**Scenario 1: Active Conversation**
```bash
SESSION_ID="active-session"

# Command 1 (starts timer)
curl ... -F "session_id=$SESSION_ID" -F "command_text=turn on ac"

# Command 2 (within 50 seconds - resets timer)
curl ... -F "session_id=$SESSION_ID" -F "command_text=is ac on?"

# Session stays active as long as commands are sent within timeout period
```

**Scenario 2: Session Expiry**
```bash
SESSION_ID="expired-session"

# Command 1
curl ... -F "session_id=$SESSION_ID" -F "command_text=turn on ac"

# Wait 60 seconds (longer than 50-second timeout)

# Command 2 - session expired, starts new conversation context
curl ... -F "session_id=$SESSION_ID" -F "command_text=is ac on?"
# Response: Won't remember the previous AC command
```

#### **Best Practices for Dynamic Timeout Management**

**For Car Systems:**
```bash
# Short city trips - quick timeout
curl -X POST "https://carplatform.dedyn.io/api/session/timeout" \
  -H "X-API-Key: your-api-key-here" \
  -d '{"timeout_seconds": 30}'

# Long highway trips - extended timeout
curl -X POST "https://carplatform.dedyn.io/api/session/timeout" \
  -H "X-API-Key: your-api-key-here" \
  -d '{"timeout_seconds": 600}'

# Parking mode - memory conservation
curl -X POST "https://carplatform.dedyn.io/api/session/timeout" \
  -H "X-API-Key: your-api-key-here" \
  -d '{"timeout_seconds": 15}'
```

**For Development/Testing:**
```bash
# Interactive testing - longer timeout for manual testing
curl -X POST "https://carplatform.dedyn.io/api/session/timeout" \
  -H "X-API-Key: your-api-key-here" \
  -d '{"timeout_seconds": 300}'

# Automated testing - shorter timeout for faster cleanup
curl -X POST "https://carplatform.dedyn.io/api/session/timeout" \
  -H "X-API-Key: your-api-key-here" \
  -d '{"timeout_seconds": 20}'
```

**Dynamic Adjustment During Use:**
```bash
# Start with default timeout
SESSION_ID="adaptive-session"

# For complex multi-step tasks, extend timeout
curl -X POST "https://carplatform.dedyn.io/api/session/timeout" \
  -H "X-API-Key: your-api-key-here" \
  -d '{"timeout_seconds": 180}'

# Begin complex conversation
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "command_text=plan a route with multiple stops" \
  -F "session_id=$SESSION_ID"

# After task completion, return to normal timeout
curl -X POST "https://carplatform.dedyn.io/api/session/timeout" \
  -H "X-API-Key: your-api-key-here" \
  -d '{"timeout_seconds": 50}'
```

### **🔄 Multi-Language Conversations**

```bash
SESSION_ID="multilang-$(date +%s)"

# Thai audio input, English response
curl -X POST "$API_URL" \
  -H "X-API-Key: $API_KEY" \
  -F "audio_file=@thai_command.mp3" \
  -F "session_id=$SESSION_ID" \
  -F "langChoice=en"

# English text follow-up, Thai response
curl -X POST "$API_URL" \
  -H "X-API-Key: $API_KEY" \
  -F "command_text=what did I just ask?" \
  -F "session_id=$SESSION_ID" \
  -F "langChoice=th"
```

### **📊 Session Monitoring**

```bash
# Check if session exists
curl -s -X GET "https://carplatform.dedyn.io/api/conversation-history/$SESSION_ID" \
  -H "X-API-Key: $API_KEY" | jq '.session_id'

# Count messages in session
curl -s -X GET "https://carplatform.dedyn.io/api/conversation-history/$SESSION_ID" \
  -H "X-API-Key: $API_KEY" | jq '.chat_history | length'
```

**Key Point**: Use the same `session_id` across all related commands to maintain conversation continuity, just like the frontend interface!

## Language Support

The API provides comprehensive multi-language support:

### **Audio Input**:
- **Automatic Language Detection**: Whisper automatically detects and transcribes Thai, English, and other languages
- **No Configuration Needed**: Works with any supported language input without specifying the audio language

### **Response Output**:
- **English Responses**: Set `langChoice=en` for English responses
- **Thai Responses**: Set `langChoice=th` for Thai responses
- **Mixed Usage**: Thai audio input can get English response and vice versa

### **Example Scenarios**:
- Thai audio → English response: `langChoice=en`
- English audio → Thai response: `langChoice=th`
- Thai audio → Thai response: `langChoice=th`
- English audio → English response: `langChoice=en`

### **Language Detection Notes**:
- **Real Human Speech**: Whisper accurately detects Thai, English, and 90+ other languages
- **Synthetic TTS Audio**: May require longer phrases or multiple words for accurate detection
- **Recommended Models**:
  - `small` model: Best balance of speed and language detection accuracy
  - `base` model: Faster but may have occasional detection issues with synthetic audio
  - `medium/large` models: Highest accuracy for challenging audio

## Transcription Speed Optimization

The API supports multiple Whisper models with different speed/accuracy tradeoffs:

### Available Models:
- **tiny**: ~32x realtime (fastest, ~39 MB, lowest accuracy)
- **base**: ~16x realtime (good balance, ~142 MB, good accuracy) ⭐ **Recommended for car commands**
- **small**: ~6x realtime (better accuracy, ~466 MB)
- **medium**: ~2x realtime (high accuracy, ~1.5 GB)
- **large**: ~1x realtime (highest accuracy, ~2.9 GB)
- **turbo**: ~8x realtime (optimized large, ~2.9 GB)

### Speed Optimization Endpoints:

#### Get Current Model Info:
```bash
curl -X GET "https://carplatform.dedyn.io/api/whisper/model-info/" \
  -H "X-API-Key: your-api-key-here"
```

**Example Response:**
```json
{
  "current_model": "small",
  "model_loaded": true,
  "available_models": {
    "tiny": {"speed": "~32x realtime", "accuracy": "lowest", "size": "~39 MB"},
    "base": {"speed": "~16x realtime", "accuracy": "good", "size": "~142 MB"},
    "small": {"speed": "~6x realtime", "accuracy": "better", "size": "~466 MB"},
    "medium": {"speed": "~2x realtime", "accuracy": "high", "size": "~1.5 GB"},
    "large": {"speed": "~1x realtime", "accuracy": "highest", "size": "~2.9 GB"},
    "turbo": {"speed": "~8x realtime", "accuracy": "high", "size": "~2.9 GB"}
  },
  "recommendations": {
    "car_commands": "tiny or base (fast response needed)",
    "voice_notes": "small or medium (better accuracy)",
    "transcription_quality": "large or turbo (highest accuracy)"
  }
}
```

#### Switch Model Dynamically:
```bash
# Switch to small model (recommended for multi-language detection)
curl -X POST "https://carplatform.dedyn.io/api/whisper/switch-model/?model_size=small" \
  -H "X-API-Key: your-api-key-here"

# Switch to base model for faster car commands
curl -X POST "https://carplatform.dedyn.io/api/whisper/switch-model/?model_size=base" \
  -H "X-API-Key: your-api-key-here"

# Switch to tiny for maximum speed (may reduce accuracy)
curl -X POST "https://carplatform.dedyn.io/api/whisper/switch-model/?model_size=tiny" \
  -H "X-API-Key: your-api-key-here"

# Switch to medium for better accuracy
curl -X POST "https://carplatform.dedyn.io/api/whisper/switch-model/?model_size=medium" \
  -H "X-API-Key: your-api-key-here"
```

**Available Models**: `tiny`, `base`, `small`, `medium`, `large`, `turbo`

**Success Response:**
```json
{
  "message": "Successfully switched to small model",
  "previous_model": "base",
  "new_model": "small",
  "model_loaded": true
}
```

### Environment Configuration:
Set the default model size using environment variable:
```bash
export WHISPER_MODEL_SIZE=base  # or tiny, small, medium, large, turbo
```

### Model Selection Guide:

#### **For Car Commands (Recommended):**
```bash
# Small model - Best for multi-language environments
curl -X POST "https://carplatform.dedyn.io/api/whisper/switch-model/?model_size=small" \
  -H "X-API-Key: your-api-key-here"
```
- **Speed**: ~3-4 seconds
- **Languages**: Excellent Thai/English detection
- **Use Case**: International cars, mixed languages

#### **For Maximum Speed:**
```bash
# Base model - Fastest reliable option
curl -X POST "https://carplatform.dedyn.io/api/whisper/switch-model/?model_size=base" \
  -H "X-API-Key: your-api-key-here"
```
- **Speed**: ~1.5-2 seconds
- **Languages**: Good English, decent Thai
- **Use Case**: English-primary environments

#### **For Best Accuracy:**
```bash
# Medium model - High accuracy
curl -X POST "https://carplatform.dedyn.io/api/whisper/switch-model/?model_size=medium" \
  -H "X-API-Key: your-api-key-here"
```
- **Speed**: ~5-8 seconds
- **Languages**: Excellent all languages
- **Use Case**: Critical accuracy needed

### Performance Comparison:
| Model | Speed | Thai Detection | English Detection | File Size |
|-------|-------|----------------|-------------------|-----------|
| **tiny** | ~1s | ⚠️ Poor | ✅ Good | 39 MB |
| **base** | ~2s | ⚠️ Fair | ✅ Excellent | 142 MB |
| **small** | ~4s | ✅ Excellent | ✅ Excellent | 466 MB |
| **medium** | ~8s | ✅ Excellent | ✅ Excellent | 1.5 GB |

**Production Recommendation**: Use `small` model for the best balance of speed, accuracy, and multi-language support.

## 🎙️ Voice Activity Detection (VAD) with C Library

The system includes a custom C library for advanced voice activity detection with automatic silence detection and recording termination.

### **📋 C Library Features**

#### **🔧 Core Functionality**
- **Real-time silence detection**: Automatically detects when user stops speaking
- **Volume analysis**: Calculates audio volume levels (0-32767 range)
- **Auto-stop recording**: Ends recording after configurable silence duration
- **Thread-safe operations**: Multi-threaded callback system
- **PCM audio processing**: Handles 16-bit PCM mono audio at 16kHz

#### **⚙️ Configuration Parameters**
- **Silence threshold**: 500 (adjustable amplitude threshold)
- **Minimum speech duration**: 500ms (before allowing auto-stop)
- **Silence duration for auto-stop**: 1500ms (1.5 seconds)
- **Sample rate**: 16kHz mono 16-bit PCM

### **🚀 API Endpoints for Voice Detection**

#### **1. Start Voice Detection**
```bash
curl -X POST "https://carplatform.dedyn.io/api/voice/start-detection" \
  -H "X-API-Key: your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "voice-session-123",
    "silence_threshold": 500,
    "min_speech_duration_ms": 500,
    "silence_duration_ms": 1500
  }'
```

**Response:**
```json
{
  "message": "Voice detection started successfully",
  "session_id": "voice-session-123",
  "silence_threshold": 500,
  "min_speech_duration_ms": 500,
  "silence_duration_ms": 1500
}
```

#### **2. Add Audio Samples**
```bash
curl -X POST "https://carplatform.dedyn.io/api/voice/add-samples" \
  -H "X-API-Key: your-api-key-here" \
  -F "session_id=voice-session-123" \
  -F "audio_file=@audio_chunk.wav"
```

**Response (Processing):**
```json
{
  "status": "need_more_samples",
  "message": "Need more audio samples",
  "session_id": "voice-session-123"
}
```

**Response (Auto-Stop Detected):**
```json
{
  "status": "completed",
  "message": "Voice detection completed",
  "session_id": "voice-session-123",
  "result": {
    "volume": 1250,
    "confidence": 85,
    "command": "AUTO_STOP_DETECTED",
    "duration_ms": 3500
  }
}
```

#### **3. Stop Voice Detection**
```bash
curl -X POST "https://carplatform.dedyn.io/api/voice/stop-detection/voice-session-123" \
  -H "X-API-Key: your-api-key-here"
```

#### **4. Detect Silence in Audio File**
```bash
curl -X GET "https://carplatform.dedyn.io/api/voice/detect-silence" \
  -H "X-API-Key: your-api-key-here" \
  -F "audio_file=@test_audio.wav" \
  -F "threshold=500"
```

**Response:**
```json
{
  "is_silence": false,
  "volume": 2150,
  "threshold": 500,
  "samples": 16000,
  "duration_ms": 1000
}
```

### **🔧 C Library Integration**

#### **Building the C Library**
```bash
# Compile the shared library
make

# Run tests
make test
./test_voice_recognition

# Install system-wide (optional)
sudo make install
```

#### **Library Structure**
```
voice_recognition.h     # Header file with API definitions
voice_recognition.c     # Main implementation
voice_recognition_wrapper.py  # Python wrapper
Makefile               # Build configuration
test_voice_recognition.c      # Test program
```

#### **Key C Functions**
```c
// Initialize library
int InitEx_WithLicense(const char* license_key);

// Start recognition with callback
HCLEVER recogStart(CALLBACK_Recognition callback, void* pUserData);

// Add audio samples (returns STATUS_SUCCESS when auto-stop detected)
int addSample(HCLEVER hclever, short* ipsSample, int nNumSamples);

// Stop recognition
int recogStop(HCLEVER hclever);

// Get results
recogResult_t getResult(HCLEVER hclever);

// Release resources
int release(HCLEVER hclever);

// Utility functions
int detectSilence(short* samples, int numSamples, int threshold);
int calculateVolume(short* samples, int numSamples);
```

### **🎯 Auto-Stop Logic**

#### **Detection Algorithm**
1. **Monitor audio volume**: Calculate RMS volume for each audio chunk
2. **Track speech/silence**: Maintain counters for speech and silence duration
3. **Minimum speech requirement**: Ensure at least 500ms of speech before allowing auto-stop
4. **Silence threshold**: Detect when volume drops below configurable threshold
5. **Auto-stop trigger**: Stop recording after 1.5 seconds of continuous silence

#### **Status Codes**
- `STATUS_SUCCESS (0)`: Auto-stop detected, recording complete
- `STATUS_ERR_NEEDMORESAMPLE (1)`: Need more audio data
- `STATUS_ERR_TIMEOUT (2)`: Timeout occurred
- `STATUS_RESULT (7)`: Final result available

### **🔄 Real-time Auto-Stop Integration**

The auto-stop functionality now uses **real-time streaming analysis** for immediate silence detection:

#### **🧪 Testing Real-time Stream Analysis**
```bash
# Simulate frontend sending multiple chunks
for i in {1..5}; do
  echo "Sending chunk $i..."
  curl -X POST "https://carplatform.dedyn.io/api/voice/stream-audio-chunk" \
    -H "X-API-Key: your-api-key-here" \
    -F "session_id=multi-chunk-test" \
    -F "audio_chunk=@english_ac.mp3" \
    -F "chunk_index=$i" \
    -F "silence_threshold=1000" \
    | jq '.auto_stop_suggested'
  sleep 1
done
```

**Expected Output:**
```json
Sending chunk 1...
false
Sending chunk 2...
false
Sending chunk 3...
true
```

#### **How It Works**
1. **Press Record Button**: Frontend starts recording with 1-second chunks
2. **Real-time Analysis**: Each chunk is analyzed for voice activity during recording
3. **Silence Detection**: System tracks consecutive silence chunks
4. **Auto-stop Trigger**: Recording stops after 2 seconds of continuous silence
5. **Immediate Response**: No need to wait for full recording to complete

#### **Real-time Frontend Implementation**
```javascript
// Recording with 1-second chunks for real-time analysis
mediaRecorderRef.current.start(1000); // 1000ms chunks

// Real-time VAD analysis on each chunk
mediaRecorderRef.current.ondataavailable = async (event) => {
  // Send chunk for immediate analysis
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('audio_chunk', event.data);
  formData.append('chunk_index', chunkIndex.toString());
  formData.append('silence_threshold', '1000');

  const response = await axios.post('/voice/stream-audio-chunk', formData);
  const { volume, is_silence, auto_stop_suggested } = response.data;

  // Track consecutive silence
  if (is_silence) {
    consecutiveSilenceChunks++;
    if (consecutiveSilenceChunks >= 2) { // 2 seconds of silence
      console.log('🛑 Auto-stop triggered: Extended silence detected');
      stopRecording(); // Automatically stop recording
    }
  } else {
    consecutiveSilenceChunks = 0; // Reset on speech
  }
};
```

#### **Real-time Streaming (Advanced)**
For real-time chunk processing:

```bash
curl -X POST "https://carplatform.dedyn.io/api/voice/stream-audio-chunk" \
  -H "X-API-Key: your-api-key-here" \
  -F "session_id=stream-session-123" \
  -F "audio_chunk=@chunk_001.wav" \
  -F "chunk_index=1" \
  -F "silence_threshold=500"
```

**Response:**
```json
{
  "session_id": "stream-session-123",
  "chunk_index": 1,
  "volume": 1250,
  "is_silence": false,
  "auto_stop_suggested": false,
  "silence_threshold": 500,
  "samples": 8000,
  "duration_ms": 500
}
```

#### **Testing Auto-Stop**

**📊 Expected Behavior:**
- **Volume > 500**: Detected as speech, continue recording
- **Volume < 500**: Detected as silence, trigger auto-stop after 1.5s
- **Console Output**: `🛑 Auto-stop detected by VAD system`
- **API Response**: `"auto_stop_detected": true`

## Troubleshooting

**1. Browser Requirements:**
- **Chrome/Edge**: Best compatibility (recommended)
- **Firefox**: Good compatibility
- **Safari**: Limited compatibility
- **HTTPS**: Required for production (not localhost)

**2. Common Solutions:**
- Allow microphone permissions when prompted
- Check browser settings: Settings → Privacy → Microphone
- Try a different browser (Chrome recommended)
- Ensure microphone is connected and working
- Test on a different device to isolate the issue

### Common Issues:
- **FFmpeg not found**: Install with `sudo apt install -y ffmpeg`
- **"Mic N/A 🔇"**: Check microphone permissions and audio system
- **Audio file too large**: Check `client_max_body_size` in nginx config
- **Slow transcription**: Switch to smaller Whisper model (`base` or `tiny`)
- **Language detection issues**: Use `small` model for better accuracy
- **API key errors**: Verify the X-API-Key header is correct
- **Ubuntu audio issues**: Install `alsa-utils` and `pulseaudio`

### Additional Speed Optimizations Applied:

The API automatically applies these optimizations for faster transcription:

- **Universal Language Detection**:
  - Always auto-detects input language (Thai, English, etc.)
  - No language pre-specification needed for transcription
  - `langChoice` only affects response language, not transcription speed
- **Beam Search Optimization**: Uses beam_size=1 for faster processing
- **Single Candidate**: Uses best_of=1 instead of multiple candidates
- **Deterministic Output**: Uses temperature=0 for consistent, faster results
- **Quality Thresholds**: Skips low-quality and silent segments automatically
- **FP32 Processing**: Uses FP32 instead of FP16 for better CPU performance

These optimizations provide **2-5x speed improvement** while maintaining excellent accuracy for multi-language car voice commands.

## Car Integration Workflow

For car systems integration, the recommended workflow is:

### 1. Audio Command Processing
```bash
# Car system records audio and sends to API
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "audio_file=@/tmp/voice_command.mp3" \
  -F "session_id=car-session-$(date +%s)" \
  -F "langChoice=en"
```

### 2. Text Command Processing
```bash
# For text-based commands from car interface
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: your-api-key-here" \
  -F "command_text=navigate to nearest gas station" \
  -F "session_id=car-session-$(date +%s)" \
  -F "lat=13.7563" \
  -F "lng=100.5018"
```

### 3. Response Processing
The API returns a structured response that car systems can parse:
- `command`: 8-digit code for car system execution
- `reply`: Text response for TTS (text-to-speech)
- `openEndedValue`: Extracted parameters for system use

### 4. Session Management
Use consistent session IDs to maintain conversation context:
```bash
SESSION_ID="car-$(hostname)-$(date +%Y%m%d)"
```

## Integration Examples

### Shell Script for Car System
```bash
#!/bin/bash
API_KEY="your-api-key-here"
API_URL="https://carplatform.dedyn.io/api/process-command-unified/"
SESSION_ID="car-$(hostname)-$(date +%Y%m%d)"

# Sample function to send audio command
send_audio_command() {
    local audio_file="$1"
    curl -X POST "$API_URL" \
        -H "X-API-Key: $API_KEY" \
        -F "audio_file=@$audio_file" \
        -F "session_id=$SESSION_ID" \
        -F "langChoice=en"
}

# Sample function to send text command
send_text_command() {
    local command="$1"
    curl -X POST "$API_URL" \
        -H "X-API-Key: $API_KEY" \
        -F "command_text=$command" \
        -F "session_id=$SESSION_ID" \
        -F "langChoice=en"
}

# Usage examples
# send_audio_command "/tmp/voice_command.mp3"
# send_text_command "turn on the headlights"
```
