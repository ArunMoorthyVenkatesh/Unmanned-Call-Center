# ABC Car Service Center — AI Customer Portal

An AI-powered unmanned customer service portal for **ABC Car Service Center**. Customers call in via phone (Twilio VoIP) or use the web interface to book service appointments, ask questions, and get car maintenance advice — all handled by an AI assistant named **Sarah**.

---

## Overview

Sarah is a conversational AI receptionist who:
- Greets customers and handles the full appointment booking flow by voice
- Collects name, vehicle details, service type, date/time, then contact info (phone + email)
- Saves appointments to AWS DynamoDB and sends SMS + email confirmations
- Sends reminders 24 hours, 3 hours, and 1 hour before the appointment
- Answers general car maintenance and service questions
- Works via both the web UI (voice + text) and inbound phone calls (Twilio VoIP)

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python) — `backend/api_car.py` |
| Frontend | React + Vite — `frontend/src/` |
| AI | Google Gemini 2.5 Flash Lite (conversation + routing) |
| Speech Recognition | Browser Web Speech API (real-time, zero latency) |
| Database | AWS DynamoDB — table `CarServiceAppointments` |
| VoIP | Twilio — inbound call handling in `backend/voip.py` |
| Notifications | AWS SES (email) + Twilio SMS |
| Reminders | APScheduler — 24hr, 3hr, 1hr before appointment |

---

## Local Development

### Backend

```bash
cd backend
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
python api_car.py
# Runs on http://localhost:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:5173
```

> **Before deploying to EC2**, set `API_BASE_URL = '/api'` in `frontend/src/App.jsx` (not `localhost:8000`).

---

## Environment Variables

Create `backend/.env` with the following keys:

```env
GEMINI_API_KEY=
GROQ_API_KEY=
WEATHER_API_KEY=
SERPAPI_API_KEY=
API_KEY=nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM

TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=

AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=ap-southeast-1
DYNAMODB_TABLE_NAME=CarServiceAppointments
SES_SENDER_EMAIL=
```

> Never commit `.env` to version control.

---

## API Authentication

All endpoints require the `X-API-Key` header (except `/voip/*` and `/`):

```bash
-H "X-API-Key: nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM"
```

---

## Key Endpoints

### Chat / Appointment Booking

```
POST /process-command-unified/
```

Handles both text and voice (transcribed) commands. Parameters:

| Field | Type | Description |
|---|---|---|
| `command_text` | string | Text message from customer |
| `session_id` | string | Session ID for conversation continuity |
| `langChoice` | string | `en` (English) or `th` (Thai) |

**Response:**
```json
{
  "command": "11111111",
  "reply": "Sarah's response text",
  "openEndedValue": null
}
```

### Session Management

```
GET  /conversation-history/{session_id}
POST /reset-conversation/{session_id}
```

### Appointments Dashboard

```
GET /appointments
```

Returns all appointments from DynamoDB for the admin dashboard.

### VoIP (Twilio)

```
POST /voip/incoming-call   — Twilio webhook for inbound calls
POST /voip/gather          — Handles speech input during call
```

---

## Appointment Booking Flow

Sarah collects information in this exact order:

1. **Name** — shown as a text input field in the web UI
2. **Vehicle** — make, model, year (by voice)
3. **Service type** — oil change, brake check, etc. (by voice)
4. **Preferred date** (by voice)
5. **Preferred time** — 8 AM–5 PM, Mon–Sat (by voice)
6. **Phone number** — shown as a text input field
7. **Email address** — shown as a text input field
8. **Confirmation** — Sarah reads back all details
9. **Goodbye** — conversation ends automatically after confirmation

---

## Web UI Features

- **Voice mode** — press Start Conversation, Sarah greets and listens automatically
- **Real-time transcription** — speech appears live as you talk (browser Web Speech API)
- **Auto-listen** — after Sarah finishes speaking, mic activates again automatically
- **Text fields** — appear contextually when Sarah asks for name, phone, or email
- **Auto-end** — conversation closes automatically after booking is confirmed
- **Text mode** — full chat interface as fallback
- **Appointments dashboard** — view and manage all bookings
- **Dark / light theme toggle**
- **English / Thai language toggle**

---

## EC2 Deployment

```bash
# SSH into server
ssh -i "backend/prdsc-sg.pem" ubuntu@ec2-47-130-32-171.ap-southeast-1.compute.amazonaws.com

# Deploy frontend
cd /home/ubuntu/app/frontend
npm run build
sudo rm -rf /var/www/html/*
sudo cp -r dist/* /var/www/html/
sudo systemctl restart nginx

# Deploy backend
sudo systemctl restart carplatform
sudo journalctl -u carplatform -f
```

---

## Project Structure

```
backend/
  api_car.py              Main FastAPI application
  voip.py                 Twilio VoIP call handler
  reminders.py            APScheduler SMS/email reminders
  appointments_db.py      DynamoDB read/write
  car_manual.pdf          Service manual for semantic search
  car_commands.csv        Command definitions
  car_specifications.csv  Service center information
  jokes.csv               Sarah's jokes (EN + TH)
  requirements.txt

frontend/
  src/
    App.jsx               Main React app (voice + text UI)
    App.css               Styling (dark/light themes)
    components/
      AppointmentDashboard.jsx
```

---

## Troubleshooting

| Issue | Fix |
|---|---|
| Port 8000 in use | `lsof -ti:8000 \| xargs kill -9` |
| `serpapi` import error | `pip uninstall serpapi google-search-results -y && pip install google-search-results` |
| Voice not working | Use Chrome or Edge (Web Speech API required) |
| TTS sounds robotic | Browser will use best available voice automatically; macOS Samantha or Google UK Female preferred |
| Appointments not saving | Check DynamoDB credentials and table name in `.env` |
| SMS/email not sending | Verify Twilio and SES credentials; SES sender email must be verified |
