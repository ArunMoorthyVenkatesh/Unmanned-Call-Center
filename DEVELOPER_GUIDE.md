# Developer Guide - Car Assistant Platform

## Architecture Overview

This is an AI-powered in-car voice assistant platform built with:
- **Frontend:** React + Vite
- **Backend:** FastAPI (Python)
- **AI Models:** Google Gemini 2.5 Flash Lite (routing & responses), Groq Whisper (transcription)
- **APIs:** OpenWeather, SerpAPI, Thai Lottery API
- **Deployment:** EC2 (Ubuntu) with Nginx reverse proxy

---

## Project Structure

```
car_panasonic/
├── backend/
│   ├── api_car.py              # Main FastAPI application
│   ├── car_commands.csv        # Car control commands database
│   ├── car_specifications.csv  # Car specifications database
│   ├── dealerships.csv         # Dealership locations (branch-specific)
│   ├── jokes.csv               # Jokes database
│   └── requirements.txt        # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.jsx            # Main React component (⚠️ API URL config here)
│   │   └── ...
│   ├── package.json
│   └── vite.config.js
├── DEVELOPER_GUIDE.md         # Technical documentation
└── README.md                  # Project overview
```

---

## API Endpoints

### Main Endpoint

**POST** `/process-command-unified/`

Unified endpoint for processing text commands or audio files.

**Headers:**
```
X-API-Key: nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM
Content-Type: application/json
```

**Request Body (Text Command):**
```json
{
  "command_text": "what's the weather tomorrow",
  "lat": 13.7563,
  "lng": 100.5018,
  "session_id": "user-session-123",
  "langChoice": "en"
}
```

**Request Body (Audio File):**
```
Content-Type: multipart/form-data

audio_file: [WAV file]
lat: 13.7563
lng: 100.5018
session_id: user-session-123
langChoice: en
```

**Response:**
```json
{
  "command": "11111111",
  "reply": "Tomorrow's forecast shows...",
  "openEndedValue": null
}
```

### Command Codes

| Code | Meaning |
|------|---------|
| `11111110` | Car manual/commands response |
| `11111111` | General information response |
| `null` | Error occurred |

For other code numbers and their meaning, refer to `car_commands.csv`.

---

## Smart Query Routing

The system uses Gemini Flash Lite to intelligently route queries to the appropriate data source:

### Data Sources

1. **Weather API** - Current weather, forecasts, air pollution
2. **Local Search API** - Nearby places (restaurants, gas stations, etc.)
3. **Lottery API** - Thai lottery results
4. **Car Manual PDF** - Semantic search for "how to" questions
5. **Car Commands CSV** - Direct car control commands
6. **Jokes CSV** - Joke requests
7. **Dealership Database** - Find nearest dealership
8. **Web Search** - General knowledge via SerpAPI

### Weather Query Types

| Query Type | API Endpoint | Example Query |
|------------|--------------|---------------|
| `current` | `/data/2.5/weather` | "what's the weather" |
| `hourly_forecast` | `/data/2.5/forecast/hourly` | "hourly forecast" |
| `daily_forecast` | `/data/2.5/forecast/daily` | "will it rain tomorrow" |
| `5day_forecast` | `/data/2.5/forecast` | "5 day forecast" |
| `air_pollution_current` | `/data/2.5/air_pollution` | "air quality" |
| `air_pollution_forecast` | `/data/2.5/air_pollution/forecast` | "air pollution tomorrow" |
| `air_pollution_historical` | `/data/2.5/air_pollution/history` | "air quality yesterday" |

---

## Performance Optimizations

### Semantic Search (Car Manual)

Optimisable parameters for fast response times:

```python
top_k = 3             
min_similarity = 0.25 
max_pages = 3         
max_chars_per_page = 800  
```

### Lottery Results

Intelligent filtering instead of retrieving entire dataset:

```python
# Only retrieve results matching user's query
filtered_results = [r for r in results if matches_query(r, command_text)]
```

---

## Branches

There are three main branches: `main`, `honda`, and `jap`. Each of them have different functionalities.

| Branch | Data |
|--------|------|
| `main` | Toyota car details, English and Thai responses only |
| `honda` | Honda car details, English and Thai responses only |
| `jap` | Toyota car details, English, Thai and Japanese responses |

### Differences in data files 

### `dealerships.csv`

**Branch-specific file** - Different functionalities per branch:

| Branch | Data |
|--------|------|
| `main` | Toyota dealership locations |
| `honda` | Honda dealership locations |

### `car_specifications.csv`

Car specifications csv file containing Toyota's details is currently also used for the honda branch. If needed, it can be modified for the honda branch later on.

### `car_manual.pdf`

Due to the PDFs being too large, it is not included in the repository during push/pull. Ensure you regenerate the embeddings for every time a different PDF is used for different car models, before pushing them to the EC2 server.

---

## Environment-Specific Configuration

### Local Development

**Backend:**
```bash
cd backend
python api_car.py
```

**Frontend (`App.jsx`):**
```javascript
const API_URL = "http://localhost:8000";
```

### EC2 Production

#### Access server (ensure to add your IP to the security group in the EC2 console)

```bash
chmod 400 "prdsc-sg.pem"

ssh -i "prdsc-sg.pem" ubuntu@ec2-47-130-32-171.ap-southeast-1.compute.amazonaws.com
```

#### Reclone files from your computer to EC2 server (ensure the frontend URL is correct as shown)

**Frontend (`App.jsx`):**
```javascript
const API_URL = "/api";
```

```bash
chmod 400 "prdsc-sg.pem"

scp -i prdsc-sg.pem ./[file name] \
ubuntu@ec2-47-130-32-171.ap-southeast-1.compute.amazonaws.com:/home/ubuntu/app/backend 
```

OR (depending on target file location)

```bash
scp -i prdsc-sg.pem ./[file name] \
ubuntu@ec2-47-130-32-171.ap-southeast-1.compute.amazonaws.com:/home/ubuntu/app/frontend
```

#### Restart frontend on EC2 after any changes

```bash
cd /home/ubuntu/app/frontend
npm run build
sudo rm -rf /var/www/html/*
sudo cp -r dist/* /var/www/html/
sudo systemctl restart nginx
sudo systemctl status nginx #to verify it is up and running
```

#### Restart backend on EC2 after any changes

```bash
sudo systemctl restart carplatform
sudo journalctl -u carplatform -f #to check logs and verify it is up and running
```

---

## Session Management

The system maintains conversation history per session:

```python
session = get_or_create_session(session_id)
session.add_message("user", command_text)
session.add_message("assistant", reply)
context = session.get_context_for_gemini(command_text)
```

**Session Features:**
- Provides context to Gemini for follow-up questions
- Separate sessions per user

---

## Audio Processing

### Supported Formats

- **Input:** WAV files (recommended: 16kHz, mono)
- **Transcription:** Groq Whisper API
- **Languages:** English (`en`), Thai (`th`), but Whisper also has auto detection for other languages.

### Audio Endpoint Usage (local testing)

```bash
curl -X POST "http://localhost:8000/process-command-unified/" \
  -H "X-API-Key: nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM" \
  -F "audio_file=@recording.wav" \
  -F "lat=13.7563" \
  -F "lng=100.5018" \
  -F "session_id=user-123" \
  -F "langChoice=en"
```

### Audio Endpoint Usage (EC2 testing)

```bash
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM" \
  -F "audio_file=@recording.wav" \
  -F "lat=13.7563" \
  -F "lng=100.5018" \
  -F "session_id=user-123" \
  -F "langChoice=en"
```

---

## Testing

### Test Queries

```bash
# Weather
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM" \
  -H "Content-Type: application/json" \
  -d '{"command_text": "will it rain tomorrow", "lat": 13.7563, "lng": 100.5018, "session_id": "test", "langChoice": "en"}'

# Air Quality
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM" \
  -H "Content-Type: application/json" \
  -d '{"command_text": "air pollution tomorrow", "lat": 13.7563, "lng": 100.5018, "session_id": "test", "langChoice": "en"}'

# Car Manual
curl -X POST "https://carplatform.dedyn.io/api/process-command-unified/" \
  -H "X-API-Key: nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM" \
  -H "Content-Type: application/json" \
  -d '{"command_text": "how to fasten seat belt", "lat": 13.7563, "lng": 100.5018, "session_id": "test", "langChoice": "en"}'
```

For more information on endpoints, refer to `README.md`.

---

**Last Updated:** 01-12-2025