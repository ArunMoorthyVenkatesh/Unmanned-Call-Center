# CLAUDE.md — Car Service Center (Unmanned VoIP Platform)

## Project Overview
AI-powered unmanned car service center. Customers call in via Twilio VoIP or use the web UI (text/voice) to schedule appointments. An AI assistant named **Sarah** handles the conversation, saves appointments to DynamoDB, and sends SMS/email confirmations + reminders.

## Stack
- **Backend:** FastAPI (Python), `backend/api_car.py` is the entry point
- **Frontend:** React + Vite, plain CSS (`frontend/src/`)
- **AI:** Google Gemini 2.5 Flash Lite (chat/routing), Groq Whisper (transcription)
- **Database:** AWS DynamoDB — table `CarServiceAppointments`, partition key `appointment_id` (UUID string, NOT integer)
- **VoIP:** Twilio — router in `backend/voip.py`, prefix `/voip`
- **Notifications:** AWS SES (email) + Twilio SMS
- **Reminders:** APScheduler BackgroundScheduler — 24hr, 3hr, 1hr before appointment (`backend/reminders.py`)

## Local Dev

### Backend
```bash
cd backend
source env/bin/activate   # or: python3 -m venv env && pip install -r requirements.txt
python api_car.py
# runs on http://localhost:8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# runs on http://localhost:5173
```

## API Key
All endpoints require `X-API-Key: nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM` (except `/voip/*` and `/`).

## Environment Variables
File: `backend/.env` — never commit this file.

Required keys:
```
GEMINI_API_KEY
GROQ_API_KEY
WEATHER_API_KEY
SERPAPI_API_KEY        # use google-search-results package, NOT serpapi
API_KEY
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_PHONE_NUMBER
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_REGION=ap-southeast-1
DYNAMODB_TABLE_NAME=CarServiceAppointments
SES_SENDER_EMAIL
```

## Key Conventions

### DynamoDB
- `appointment_id` is a **UUID string** — never use integers
- `save_appointment()` returns the UUID string
- `update_appointment_status(id, status)` takes a string ID

### VoIP State Machine (`backend/voip.py`)
States: `greeting → name → phone → email → vehicle → service → date → time → confirming → done`
- Sessions stored in-memory dict keyed by Twilio `CallSid`
- On `save_appointment=true`: saves to DynamoDB, sends confirmation, schedules reminders

### Reminders (`backend/reminders.py`)
- Scheduler starts on app startup, stops on shutdown
- `schedule_reminders(appointment)` creates 3 jobs per appointment
- `cancel_reminders(appointment_id)` cancels all 3 when appointment is cancelled/no-show

### Frontend
- `API_BASE_URL = 'http://localhost:8000'` for local dev; change to `"/api"` for EC2
- Default mode: **voice**, default theme: **dark**
- Assistant name displayed: **Sarah**
- CSS custom properties in `App.css` — dark is `:root`, light is `[data-theme="light"]`
- Teal accent: `--teal` (`#19e3d2` dark / `#00897b` light)

## EC2 Deployment
```bash
# SSH
ssh -i "prdsc-sg.pem" ubuntu@ec2-47-130-32-171.ap-southeast-1.compute.amazonaws.com

# Before deploying frontend — set API URL to /api in App.jsx
const API_BASE_URL = '/api';

# Deploy frontend
cd /home/ubuntu/app/frontend && npm run build
sudo rm -rf /var/www/html/* && sudo cp -r dist/* /var/www/html/
sudo systemctl restart nginx

# Deploy backend
sudo systemctl restart carplatform
sudo journalctl -u carplatform -f
```

## Claude Skills (Slash Commands)

Available skills you can invoke with `/skill-name` in Claude Code:

| Skill | Trigger | What it does |
|-------|---------|--------------|
| `/simplify` | After writing or editing code | Reviews changed code for reuse, quality, and efficiency — then fixes issues found |
| `/loop` | When you need a recurring task | Runs a prompt or command on an interval (e.g. `/loop 5m /simplify`). Default interval: 10 min |
| `/claude-api` | When adding Claude/Anthropic SDK code | Guides building apps with the Claude API or Anthropic SDK. Auto-triggers when code imports `anthropic` or `@anthropic-ai/sdk` |
| `/keybindings-help` | To customise keyboard shortcuts | Rebind keys, add chord bindings, or modify `~/.claude/keybindings.json` |

### Usage examples
```
/simplify                          # review last code change
/loop 10m /simplify                # re-review every 10 minutes
/claude-api                        # help integrating Anthropic SDK
/keybindings-help                  # customise Claude Code shortcuts
```

## Common Pitfalls
- **serpapi package conflict**: use `google-search-results` only. If `from serpapi import GoogleSearch` fails, run `pip uninstall serpapi google-search-results -y && pip install google-search-results`
- **`appointment_id` must be str**: DynamoDB uses UUID strings, not ints
- **`/voip/*` routes are excluded from API key middleware** — do not add auth to them
- **Reminder jobs**: always cancel on appointment status change to `cancelled` or `no_show`
