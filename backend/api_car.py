import os
from dotenv import load_dotenv
load_dotenv()  # MUST be first — loads .env before any module reads os.getenv()

import logging
import re
import json
from datetime import datetime, timedelta
from typing import Optional
from groq import Groq

import google.generativeai as genai
from voip import router as voip_router, send_confirmation
from appointments_db import init_db, get_all_appointments, update_appointment_status, save_appointment, get_available_slots, is_slot_available, ALL_SLOTS, MAX_APPOINTMENTS_PER_DAY
from reminders import start_scheduler, stop_scheduler, cancel_reminders, schedule_reminders

from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
import uuid

# --- Configuration ---
init_db()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
API_KEY = os.getenv("API_KEY")

GROQ_CLIENT = None
TRANSCRIPTION_MODEL = "whisper-large-v3-turbo"

if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY must be set in your .env file.")

CONVERSATION_SESSIONS = {}
SESSION_TIMEOUT = timedelta(seconds=300)

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Gemini Configuration ---
MODEL_NAME_GEMINI = 'models/gemini-2.5-flash-lite'
gemini_model = None

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel(MODEL_NAME_GEMINI)
        logger.info(f"Gemini model '{MODEL_NAME_GEMINI}' initialized.")
    except Exception as e:
        logger.error(f"Error initializing Gemini model '{MODEL_NAME_GEMINI}': {e}", exc_info=True)

generation_config_gemini = genai.GenerationConfig(temperature=0.4, top_p=0.9, top_k=40, response_mime_type="application/json")
safety_settings_gemini = []

async def initialize_groq_client():
    """Initialize the Groq client for audio transcription"""
    global GROQ_CLIENT, GROQ_API_KEY
    try:
        if not GROQ_API_KEY:
            logger.error("GROQ_API_KEY not set in environment variables")
            return False

        logger.info("Initializing Groq client...")
        GROQ_CLIENT = Groq(api_key=GROQ_API_KEY)
        logger.info("Groq client initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Error initializing Groq client: {e}")
        return False

async def transcribe_audio(audio_data: bytes, filename: str = "audio.mp3", fast_mode: bool = True) -> dict:
    """Transcribe audio file using Groq Whisper API - always auto-detects language

    Args:
        audio_data: Raw audio file bytes
        filename: Original filename (used for format detection)
        fast_mode: Not used, kept for compatibility
    """
    global GROQ_CLIENT

    if GROQ_CLIENT is None:
        logger.error("Groq client not initialized")
        return {"error": "Groq client not available"}

    try:
        logger.info(f"Transcribing audio directly from memory: {filename} ({len(audio_data)} bytes) using Groq {TRANSCRIPTION_MODEL}")

        # Create a file-like object from bytes
        from io import BytesIO
        audio_file = BytesIO(audio_data)
        audio_file.name = filename  # Set filename for format detection

        # Use Groq's Whisper API for transcription
        transcription = GROQ_CLIENT.audio.transcriptions.create(
            file=audio_file,
            model=TRANSCRIPTION_MODEL,
            response_format="verbose_json",  # Get detailed response with language detection
            temperature=0.0
        )

        transcribed_text = transcription.text.strip()
        detected_language = getattr(transcription, 'language', 'unknown')

        logger.info(f"Transcription successful: '{transcribed_text}' (language: {detected_language})")

        return {
            "text": transcribed_text,
            "language": detected_language
        }
    except Exception as e:
        logger.error(f"Error transcribing audio with Groq Whisper API: {e}")
        return {"error": f"Transcription failed: {str(e)}"}









def create_gemini_prompt_with_search(statement="", conversation_context="", langChoice="en", gender=None, available_slots=None, chosen_date=None):
    """Create Gemini prompt with conversation context for appointment/service queries."""



    _today_str = datetime.now().strftime('%d/%m/%Y')

    # Build available slots context
    if chosen_date and available_slots is not None:
        if len(available_slots) == 0:
            slots_context = f"\n**APPOINTMENT SLOTS for {chosen_date}:** Fully booked — no slots available. Apologise and ask the customer to choose a different date.\n"
        else:
            slots_display = ", ".join(available_slots)
            slots_context = f"\n**APPOINTMENT SLOTS for {chosen_date} (AVAILABLE):** {slots_display}\nOnly offer times from this list. If the customer requests a time not in this list, apologise and offer the nearest available slot.\n"
    else:
        all_slots_display = ", ".join(ALL_SLOTS)
        slots_context = f"\n**APPOINTMENT TIME RULES:**\n- Valid slots (30-min intervals): {all_slots_display}\n- Lunch break: 12:30–14:00 — NO appointments\n- Max {MAX_APPOINTMENTS_PER_DAY} appointments per day\n- Only one appointment per slot — no double-booking\n- Once the customer provides a date, only offer slots that are actually available\n"

    lang_name = 'Thai' if langChoice == 'th' else 'English'
    honorific_line = ""
    if gender == 'M':
        honorific_line = "\n**HONORIFIC:** Address the customer as \"sir\" throughout the entire conversation. Never use \"ma'am\"."
    elif gender == 'F':
        honorific_line = "\n**HONORIFIC:** Address the customer as \"ma'am\" throughout the entire conversation. Never use \"sir\"."
    prompt = f"""

**MANDATORY LANGUAGE SETTING - APPLY IMMEDIATELY:**
- ALL responses must be in {'Thai' if langChoice == 'th' else 'English'} language
- The `reply` field MUST be in {'Thai' if langChoice == 'th' else 'English'}
- Switch language NOW - no delays or buffers{honorific_line}

{conversation_context}

{slots_context}

You are **Sarah**, a friendly and professional AI customer service assistant for **ABC Car Service Center**.

Your role is to help customers with:
- **Booking service appointments** (oil change, brake inspection, tyre rotation, general service, etc.)
- **Answering questions** about services offered, pricing, operating hours, and what to expect
- **General car maintenance advice** (brand-agnostic — do not mention Toyota or any specific brand)
- **Friendly conversation** and small talk

**WHO YOU ARE:**
- You are Sarah from ABC Car Service Center
- You are warm, professional, and concise
- You NEVER mention Toyota, Honda, BMW, or any car brand unless the customer brings it up
- You NEVER refer to yourself as an in-car assistant or pretend to be inside someone's vehicle
- You NEVER suggest finding a "nearest dealership" — you ARE the service center

**APPOINTMENT BOOKING — STRICT FLOW (follow this order exactly):**
1. Ask for their **full name** first
2. Ask for **vehicle details** (make, model, year)
3. Ask what **service** they need (oil change, brake check, etc.)
4. Ask for **preferred date** (remind: Mon–Sat only)
5. Ask for **preferred time** — ONLY offer slots from the **AVAILABLE SLOTS** list below
6. Ask for **email address** — say exactly: "And your email address please?"
7. **Read back ALL details** and ask them to confirm
9. Once confirmed: say "Your appointment is confirmed! We'll see you on [date] at [time]. Goodbye and have a great day!" — end the conversation warmly

**CRITICAL RULES:**
- **BEFORE ASKING ANYTHING** — go through this checklist using the conversation history above:
  - Do I already have their NAME? → if yes, skip asking for it
  - Do I already have their VEHICLE? → if yes, skip asking for it
  - Do I already have the SERVICE TYPE? → if yes, skip asking for it
  - Do I already have the DATE? → if yes, skip asking for it
  - Do I already have the TIME? → if yes, skip asking for it
  - Do I already have their EMAIL? → if yes, skip asking for it
  - Only ask for the FIRST missing piece of information, then stop.
- NEVER re-ask for something already given, even if it was mentioned casually or early in the conversation.
- Once you have the email address, your ONLY next step is to read back ALL appointment details and ask the customer to confirm. Do NOT ask for email again.
- After the customer confirms, say the goodbye message and end. Do NOT ask any more questions.
- Do NOT invent, suggest, or list available time slots. You do not have access to a booking calendar. Simply accept whatever date and time the customer requests.
- Do NOT ask for email before getting vehicle, service, date and time.
- The collected information flows in ONE direction only — forward. Never go backwards.
- **DATE FORMAT — MANDATORY:** Always convert the appointment date to `dd/mm/yyyy` format before saving. Today is {_today_str}. If the customer says "tomorrow" → add 1 day and format as dd/mm/yyyy. If they say "Saturday", "next Monday", etc. → calculate the actual calendar date and format as dd/mm/yyyy. The `appointment_date` field in `appointment_data` MUST always be a date in `dd/mm/yyyy` format, never a relative word.

**CONFIRMATION — READ THIS CAREFULLY:**
- After you read back all details and ask "Does all of this sound correct?", if the customer replies with ANY of the following: "yes", "yup", "yeah", "correct", "that's right", "looks good", "ok", "okay", "sure", "confirmed", "sounds good", "go ahead", "perfect", "great" — treat this as FINAL CONFIRMATION.
- On final confirmation you MUST: (1) set `save_appointment: true`, (2) populate `appointment_data`, (3) say the goodbye message. NEVER ask "Does all of this sound correct?" again.
- If you have already asked for confirmation and the customer has already answered, do NOT repeat the confirmation question under any circumstances.

**CONVERSATION CONTINUITY:**
- Always consider the conversation history above when responding
- Maintain context across the conversation
- If the customer refers to "that", "it", or previous context, use the history to understand

**OUTPUT FORMAT:**
You MUST return ONLY a JSON object:
{{
  "command": "11111111",
  "reply": "YOUR_RESPONSE_HERE",
  "openEndedValue": null,
  "save_appointment": false,
  "appointment_data": null
}}

Use `"command": "11111110"` for informational/how-to responses.
Use `"command": null` only if the request is completely outside your scope (e.g., booking a flight, doing homework).

When the customer has confirmed their appointment (step 9), return this COMPLETE JSON (all 5 fields required):
{{
  "command": "11111111",
  "reply": "Your appointment is confirmed! We'll see you on [date] at [time]. Goodbye and have a great day!",
  "openEndedValue": null,
  "save_appointment": true,
  "appointment_data": {{
    "name": "customer full name",
    "email": "email address",
    "vehicle": "make model year",
    "service_type": "type of service",
    "appointment_date": "date",
    "appointment_time": "time"
  }}
}}
CRITICAL: The confirmation JSON MUST include "command", "reply", "openEndedValue", "save_appointment", and "appointment_data" — ALL 5 fields. Never omit any field.
Set `save_appointment: true` IMMEDIATELY when the customer says yes/yup/correct/ok/confirmed/sure to the final summary. Do NOT repeat the summary question — go straight to the goodbye message with save_appointment: true.

**LANGUAGE:**
- YOUR OUTPUT reply MUST be in {'Thai' if langChoice == 'th' else 'English'}
- Accept input in any language

**JOKE SELECTION RULE:**
- When asked for a joke, select from the language-appropriate list above
- Thai jokes for langChoice="th", English jokes for langChoice="en"

**EXAMPLES:**

*   **INPUT:** `I want to book a service`
*   **OUTPUT:**
    {{
      "command": "11111111",
      "reply": "Of course! I'd be happy to help you book a service appointment. Could you please tell me your name and what type of service your car needs?",
      "openEndedValue": null
    }}

*   **INPUT:** `What services do you offer?`
*   **OUTPUT:**
    {{
      "command": "11111110",
      "reply": "At ABC Car Service Center, we offer oil changes, brake inspections, tyre rotation and balancing, full vehicle health checks, air conditioning service, battery replacement, and more. Is there a specific service you're interested in?",
      "openEndedValue": null
    }}

*   **INPUT:** `How often should I change my oil?`
*   **OUTPUT:**
    {{
      "command": "11111110",
      "reply": "Most modern cars recommend an oil change every 5,000 to 10,000 km, or every 6 months — whichever comes first. Would you like to book an oil change with us?",
      "openEndedValue": null
    }}

*   **INPUT:** `Find me the nearest Toyota dealership`
*   **OUTPUT:**
    {{
      "command": "11111111",
      "reply": "I'm Sarah from ABC Car Service Center — we can take care of your car right here! Would you like to book a service appointment with us?",
      "openEndedValue": null
    }}

*   **INPUT:** `Can you book me a flight to Japan?`
*   **OUTPUT:**
    {{
      "command": null,
      "reply": "Sorry, that's outside what I can help with. I'm here to assist with car service bookings and questions. Is there anything car-related I can help you with?",
      "openEndedValue": null
    }}

*   **INPUT:** `Increase fan speed`
*   **OUTPUT:**
    {{
      "command": "11111111",
      "reply": "I'm a service center assistant, so I can't control in-car features. But if you're having issues with your car's fan or air conditioning, I can book a service appointment for you!",
      "openEndedValue": null
    }}

*   **INPUT:** `Answer the call`
*   **OUTPUT:**
    {{
      "command": "10000010",
      "reply": "Answering the call.",
      "openEndedValue": null
    }}

*   **INPUT:** `Set the radio to 92.9`
*   **OUTPUT:**
    {{
      "command": "00001011",
      "reply": "Setting radio frequency to 92.9.",
      "openEndedValue": "92.9"
    }}

*   **INPUT:** `Help me check where the nearest gas station is`
*   **OUTPUT:**
    {{
      "command": "01100110",
      "reply": "The nearest gas station is located at [address retrieved from web search].",
      "openEndedValue": null
    }}

*   **INPUT:** `What is with the audio system of the car?`
*   **OUTPUT:**
    {{
      "command": "11111111",
      "reply": "Standard 6-speaker system; upgraded JBL 9-speaker audio system available on higher trims.",
      "openEndedValue": null
    }}

*   **INPUT:** `What is the time?`
*   **OUTPUT:**
    {{
      "command": "11111110",
      "reply": "The current time is 11:00 AM.",
      "openEndedValue": null
    }}
    
*   **INPUT:** `Tell me a joke`
*   **OUTPUT:**
    {{
      "command": "11111110",
      "reply": "What animal cries only one month? The crying shrimp in October.",
      "openEndedValue": null
    }}
    
*   **INPUT:** `Can you do my homework?`
*   **OUTPUT:**
    {{
      "command": null,
      "reply": "Sorry, I am unable to process that request with the available commands.",
      "openEndedValue": null
    }}
**Now, process the user statement:** `{statement}`
"""
    return prompt.strip()

# Pre-compiled date pattern for slot availability detection
_RE_DATE  = re.compile(r'\b(\d{2}/\d{2}/\d{4})\b')


# --- Core Command Processing Logic ---
async def get_ai_command_response(command_text: str, session_id: str = None, langChoice: str = None, gender: str = None) -> dict:
    """Process command with Gemini and conversation history."""
    if not gemini_model:
        logger.error("Gemini model not initialized. Cannot process command.")
        return {
            "command": None,
            "reply": "AI service (Gemini) is not available.",
            "openEndedValue": None,
            "error": "GEMINI_MODEL_NOT_LOADED"
        }

    session = get_or_create_session(session_id)
    session.add_message("user", command_text)
    # Use gender from session (already stored by endpoint) or passed directly
    effective_gender = session.gender or gender
    logger.info(f"Processing command with Gemini: '{command_text}' for session: {session.session_id}")

    conversation_context = session.get_context_for_gemini(command_text)

    # Extract date from conversation history (dd/mm/yyyy pattern) for slot availability
    chosen_date = None
    available_slots = None
    full_context = conversation_context + " " + command_text
    date_match = _RE_DATE.search(full_context)
    if date_match:
        chosen_date = date_match.group(1)
        available_slots = get_available_slots(chosen_date)
        logger.info(f"Date detected in context: {chosen_date}, available slots: {available_slots}")

    prompt = create_gemini_prompt_with_search(command_text, conversation_context, langChoice, gender=effective_gender, available_slots=available_slots, chosen_date=chosen_date)

    logger.info(f"Sending prompt to Gemini for: '{command_text}'")
    logger.debug(f"Prompt for Gemini: {prompt}")

    # Generate response with Gemini
    try:
        response = await gemini_model.generate_content_async(
            prompt,
            generation_config=generation_config_gemini,
            safety_settings=safety_settings_gemini
        )
        logger.info(f"Received response from Gemini for: '{command_text}'")
        logger.debug(f"Raw Gemini Response object: {response}")

        if response.prompt_feedback.block_reason:
            logger.warning(f"Gemini response blocked. Reason: {response.prompt_feedback.block_reason}.")
            return {
                "command": None,
                "reply": f"AI response generation was blocked (Reason: {response.prompt_feedback.block_reason}).",
                "openEndedValue": None,
                "error": "AI_RESPONSE_BLOCKED"
            }

        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            part = response.candidates[0].content.parts[0]
            if hasattr(part, 'text'):
                raw_text = part.text.strip()
                try:
                    # Try 1: parse raw text directly
                    try:
                        parsed_json = json.loads(raw_text)
                    except json.JSONDecodeError:
                        # Try 2: extract between first { and last }
                        start = raw_text.find('{')
                        end = raw_text.rfind('}')
                        if start != -1 and end != -1 and end > start:
                            json_str = raw_text[start:end+1]
                            logger.info(f"Extracted JSON by brace search: '{json_str[:200]}'")
                            parsed_json = json.loads(json_str)
                        else:
                            raise

                    if not all(k in parsed_json for k in ["command", "reply", "openEndedValue"]):
                        logger.warning(f"AI response missing required keys: {parsed_json}")
                        raise ValueError("Missing required keys in AI JSON response")

                    logger.info(f"Successfully parsed Gemini response: command={parsed_json.get('command')}, reply_length={len(parsed_json.get('reply', ''))}")

                    # Track partial appointment data so Sarah doesn't re-ask for collected info
                    if parsed_json.get("appointment_data") and session:
                        session.update_collected(parsed_json["appointment_data"])

                    # Save appointment when Sarah has collected all details and customer confirmed
                    if parsed_json.get("save_appointment") and parsed_json.get("appointment_data"):
                        try:
                            apt = parsed_json["appointment_data"]
                            # Double-booking guard
                            if not is_slot_available(apt.get("appointment_date", ""), apt.get("appointment_time", "")):
                                logger.warning(f"Slot conflict: {apt.get('appointment_date')} {apt.get('appointment_time')} already booked or invalid")
                                parsed_json["save_appointment"] = False
                                parsed_json["reply"] = (
                                    "I'm sorry, that time slot was just taken or is not a valid slot. "
                                    "Could you please choose a different time?"
                                )
                                session.add_message("assistant", parsed_json["reply"])
                                return parsed_json
                            apt["created_at"] = datetime.now().isoformat()
                            apt["status"]     = "confirmed"
                            apt["notes"]      = f"Booked via web portal. Session: {session_id}"
                            appointment_id = save_appointment(apt)
                            logger.info(f"Appointment saved via web chat: id={appointment_id}")

                            # Send confirmation email immediately after DB save
                            try:
                                send_confirmation(
                                    apt.get("phone", ""),
                                    apt.get("email", ""),
                                    apt,
                                    appointment_id,
                                )
                                logger.info(f"Confirmation email sent for appointment {appointment_id}")
                            except Exception as notify_err:
                                logger.error(f"Confirmation email failed: {notify_err}", exc_info=True)

                            # Schedule 24hr / 3hr / 1hr reminders
                            schedule_reminders({**apt, "appointment_id": appointment_id})

                            # Embed short ID into Sarah's reply
                            parsed_json["reply"] = parsed_json["reply"].replace(
                                "{appointment_id}", appointment_id[:8]
                            )
                        except Exception as e:
                            logger.error(f"Error saving web chat appointment: {e}")

                    # Save assistant's reply to session history
                    session.add_message("assistant", parsed_json.get("reply", ""))

                    return parsed_json
                except (json.JSONDecodeError, ValueError) as json_err:
                    logger.error(f"Failed to parse JSON from Gemini: {json_err}. Raw text: '{raw_text}'")
                    return {
                        "command": None,
                        "reply": "I'm sorry, I had trouble processing that. Could you please try again?",
                        "openEndedValue": None,
                        "error": "INVALID_AI_JSON_RESPONSE"
                    }
            else:
                logger.warning(f"First response part from Gemini is not text. Part: {part}")
                return {
                    "command": None,
                    "reply": "Error: AI response part was not text.",
                    "openEndedValue": None,
                    "error": "NON_TEXT_AI_RESPONSE_PART"
                }
        else:
            logger.warning(f"Gemini response issue: no valid candidates/content/parts. Candidates: {response.candidates}")
            return {
                "command": None,
                "reply": "Error: Received unexpected or empty response structure from AI.",
                "openEndedValue": None,
                "error": "EMPTY_OR_INVALID_AI_RESPONSE_STRUCTURE"
            }

    except genai.types.generation_types.BlockedPromptException as bpe:
        logger.error(f"Gemini Prompt Blocked: {bpe.block_reason}", exc_info=False)
        return {
            "command": None,
            "reply": f"Request blocked by AI safety settings ({bpe.block_reason}).",
            "openEndedValue": None,
            "error": "AI_PROMPT_BLOCKED"
        }
    except Exception as e:
        logger.error(f"Error during AI command processing: {e}", exc_info=True)
        return {
            "command": None,
            "reply": f"An internal error occurred while processing with AI: {str(e)}",
            "openEndedValue": None,
            "error": "INTERNAL_AI_PROCESSING_ERROR"
        }

# --- FastAPI App Setup ---
app = FastAPI(title="Car Command AI API", version="1.0.0")
app.include_router(voip_router)

# --- API Key Authentication Middleware ---
@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    """Middleware to verify API key for all requests except root endpoint"""

    # Skip API key check for root endpoint, health checks, and VoIP webhooks
    if request.url.path in ["/", "/docs", "/redoc", "/openapi.json"] or request.url.path.startswith("/voip/"):
        response = await call_next(request)
        return response

    # Get API key from header
    api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization")

    # Remove "Bearer " prefix if present
    if api_key and api_key.startswith("Bearer "):
        api_key = api_key[7:]

    # Validate API key
    if not api_key or api_key != API_KEY:
        logger.warning(f"Unauthorized access attempt from {request.client.host if request.client else 'unknown'}")
        return JSONResponse(
            status_code=401,
            content={
                "error": "UNAUTHORIZED",
                "message": "Valid API key required. Include 'X-API-Key' header or 'Authorization: Bearer <key>' header."
            }
        )

    # API key is valid, proceed with request
    response = await call_next(request)
    return response

@app.on_event("shutdown")
async def shutdown_event():
    stop_scheduler()


@app.on_event("startup")
async def startup_event():
    start_scheduler()
    await initialize_groq_client()

# --- CORS Middleware Configuration (Keep as is) ---
origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://47.130.32.171",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["*"],
)

class ConversationSession:
    TRACKED_FIELDS = ["name", "vehicle", "service_type", "appointment_date", "appointment_time", "email"]

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.chat_history = []
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.gender = None
        self.collected = {}  # Explicitly tracked appointment fields

    def add_message(self, role: str, content: str):
        self.chat_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        self.last_activity = datetime.now()

    def update_collected(self, appointment_data: dict):
        """Update collected fields from Gemini's appointment_data response."""
        for field in self.TRACKED_FIELDS:
            val = appointment_data.get(field)
            if val and str(val).strip():
                self.collected[field] = str(val).strip()

    def get_context_for_gemini(self, current_statement: str) -> str:
        """Create context string from chat history for Gemini."""
        context = ""
        if self.chat_history:
            context += "\n**CONVERSATION HISTORY:**\n"
            for msg in self.chat_history[-20:]:
                role_display = "User" if msg["role"] == "user" else "Assistant"
                context += f"{role_display}: {msg['content']}\n"

        if self.collected:
            context += "\n**ALREADY COLLECTED — DO NOT ASK FOR THESE AGAIN:**\n"
            for k, v in self.collected.items():
                context += f"  ✓ {k}: {v}\n"
            missing = [f for f in self.TRACKED_FIELDS if f not in self.collected]
            if missing:
                context += f"\n**STILL NEEDED:** {', '.join(missing)}\n"

        context += f"\n**CURRENT USER INPUT:** {current_statement}\n\n"
        return context

    def is_expired(self) -> bool:
        return datetime.now() - self.last_activity > SESSION_TIMEOUT
    

def cleanup_expired_sessions():
    """Remove expired sessions"""
    expired_sessions = [
        session_id for session_id, session in CONVERSATION_SESSIONS.items()
        if session.is_expired()
    ]
    for session_id in expired_sessions:
        del CONVERSATION_SESSIONS[session_id]

def get_or_create_session(session_id: str = None) -> ConversationSession:
    """Get existing session or create new one"""
    cleanup_expired_sessions()
    
    if session_id and session_id in CONVERSATION_SESSIONS:
        session = CONVERSATION_SESSIONS[session_id]
        if not session.is_expired():
            return session
        else:
            del CONVERSATION_SESSIONS[session_id]
    
    # Create new session
    new_session_id = session_id or str(uuid.uuid4())
    session = ConversationSession(new_session_id)
    CONVERSATION_SESSIONS[new_session_id] = session
    return session

# --- API Endpoint ---
class CommandRequest(BaseModel):
    command_text: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    session_id: Optional[str] = None
    langChoice: str

@app.post("/process-command/", response_class=JSONResponse)
async def process_command_endpoint(request_data: CommandRequest):
    """Process command using Gemini with conversation history."""
    command_text = request_data.command_text
    session_id = request_data.session_id
    langChoice = request_data.langChoice

    if not command_text:
        raise HTTPException(status_code=400, detail="command_text cannot be empty")

    logger.info(f"Received API request: '{command_text}', session: {session_id}, langChoice: {langChoice}")

    ai_response_dict = await get_ai_command_response(command_text, session_id=session_id, langChoice=langChoice)

    if "error" in ai_response_dict:
        logger.error(f"Error processing command '{command_text}': {ai_response_dict.get('reply')}")
        status_code = 500
        if ai_response_dict.get("error") == "GEMINI_MODEL_NOT_LOADED":
            status_code = 503
        return JSONResponse(status_code=status_code, content=ai_response_dict)

    return JSONResponse(status_code=200, content=ai_response_dict)

@app.post("/process-command-unified/", response_class=JSONResponse)
async def process_command_unified_endpoint(
    command_text: Optional[str] = Form(None),
    audio_file: Optional[UploadFile] = File(None),
    session_id: Optional[str] = Form(None),
    langChoice: str = Form("en"),
    gender: Optional[str] = Form(None),
    enable_auto_stop: Optional[bool] = Form(False),
    silence_threshold: Optional[int] = Form(500),
    min_speech_duration_ms: Optional[int] = Form(500),
    silence_duration_ms: Optional[int] = Form(1500)
):
    """Unified endpoint that can process either text commands or audio files with API key validation"""

    # Validate that either text or audio is provided, but not both
    if not command_text and not audio_file:
        return JSONResponse(
            status_code=400,
            content={"error": "Missing input", "reply": "Please provide either command_text or audio_file."}
        )

    if command_text and audio_file:
        return JSONResponse(
            status_code=400,
            content={"error": "Multiple inputs", "reply": "Please provide either command_text OR audio_file, not both."}
        )

    # If audio file is provided, transcribe it first
    if audio_file:
        if GROQ_CLIENT is None:
            return JSONResponse(
                status_code=503,
                content={"error": "Groq client not available", "reply": "Audio transcription service is not available."}
            )

        # Validate file type - be more flexible with audio types
        valid_audio_types = ['audio/', 'video/webm', 'video/mp4']
        is_valid_audio = False

        if audio_file.content_type:
            is_valid_audio = any(audio_file.content_type.startswith(audio_type) for audio_type in valid_audio_types)

        # Also check file extension as fallback
        if not is_valid_audio and audio_file.filename:
            valid_extensions = ['.mp3', '.wav', '.m4a', '.webm', '.ogg', '.flac', '.aac']
            is_valid_audio = any(audio_file.filename.lower().endswith(ext) for ext in valid_extensions)

        if not is_valid_audio:
            logger.warning(f"Invalid audio file type: {audio_file.content_type}, filename: {audio_file.filename}")
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid file type", "reply": "Please upload an audio file (mp3, wav, webm, etc.)."}
            )

        # Process audio file - directly without saving to temp file
        try:
            # Read audio data
            audio_data = await audio_file.read()
            logger.info(f"Processing audio file directly: {audio_file.filename} (size: {len(audio_data)} bytes, type: {audio_file.content_type})")

            # Transcribe the audio directly from memory (auto-detects language)
            transcription_result = await transcribe_audio(audio_data, filename=audio_file.filename or "audio.mp3", fast_mode=True)

            if "error" in transcription_result:
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": transcription_result["error"],
                        "reply": "Failed to transcribe audio. Please try again."
                    }
                )

            command_text = transcription_result["text"]
            if not command_text.strip():
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "No speech detected",
                        "reply": "No speech was detected in the audio. Please try speaking more clearly."
                    }
                )

            logger.info(f"Audio transcribed successfully: '{command_text}'")

        except Exception as e:
            logger.error(f"Error processing audio file: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": f"Audio processing failed: {str(e)}",
                    "reply": "Failed to process audio file. Please try again."
                }
            )

    # Now process the command (either original text or transcribed from audio)
    if not command_text.strip():
        raise HTTPException(status_code=400, detail="command_text cannot be empty")

    logger.info(f"Processing command: '{command_text}', session: {session_id}, langChoice: {langChoice}")

    # Persist gender on session if provided
    if gender and session_id:
        sess = get_or_create_session(session_id)
        if gender in ('M', 'F'):
            sess.gender = gender

    ai_response_dict = await get_ai_command_response(command_text, session_id=session_id, langChoice=langChoice)

    # Add transcription info if audio was used
    if audio_file:
        ai_response_dict["transcribed_text"] = command_text
        ai_response_dict["input_type"] = "audio"
        # Add VAD information if it was processed
        # if 'vad_info' in locals():
        #     ai_response_dict["vad_info"] = vad_info
        #     if 'auto_stop_detected' in locals():
        #         ai_response_dict["auto_stop_detected"] = auto_stop_detected
    else:
        ai_response_dict["input_type"] = "text"

    if "error" in ai_response_dict:
        logger.error(f"Error processing command '{command_text}': {ai_response_dict.get('reply')}")
        status_code = 500
        if ai_response_dict.get("error") == "GEMINI_MODEL_NOT_LOADED":
            status_code = 503
        return JSONResponse(status_code=status_code, content=ai_response_dict)

    return JSONResponse(status_code=200, content=ai_response_dict)

@app.get("/transcription/info/", response_class=JSONResponse)
async def get_transcription_info():
    """Get current transcription service information"""
    return JSONResponse(
        status_code=200,
        content={
            "service": "Groq Whisper API",
            "model": TRANSCRIPTION_MODEL,
            "client_initialized": GROQ_CLIENT is not None,
            "features": {
                "language_detection": "Automatic (verbose_json)",
                "supported_formats": ["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm", "flac"],
                "max_file_size": "25 MB",
                "speed": "Cloud-based (very fast - Turbo)",
                "accuracy": "High (Whisper Large V3 Turbo)"
            }
        }
    )

@app.post("/transcribe-audio/", response_class=JSONResponse)
async def transcribe_audio_endpoint(
    audio_file: UploadFile = File(...)
):
    """Transcribe audio file using Groq Whisper API - returns only transcription and detected language"""

    if GROQ_CLIENT is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Groq client not available"}
        )

    # Validate file type - be more flexible with audio types
    valid_audio_types = ['audio/', 'video/webm', 'video/mp4']  # Include webm for browser recordings
    is_valid_audio = False

    if audio_file.content_type:
        is_valid_audio = any(audio_file.content_type.startswith(audio_type) for audio_type in valid_audio_types)

    # Also check file extension as fallback
    if not is_valid_audio and audio_file.filename:
        valid_extensions = ['.mp3', '.wav', '.m4a', '.webm', '.ogg', '.flac', '.aac']
        is_valid_audio = any(audio_file.filename.lower().endswith(ext) for ext in valid_extensions)

    if not is_valid_audio:
        logger.warning(f"Invalid audio file type: {audio_file.content_type}, filename: {audio_file.filename}")
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid file type. Please upload an audio file (mp3, wav, webm, etc.)."}
        )

    # Process audio file directly without temp file
    try:
        # Read audio data
        audio_data = await audio_file.read()
        logger.info(f"Transcribing audio file: {audio_file.filename} (size: {len(audio_data)} bytes, type: {audio_file.content_type})")

        # Transcribe the audio directly from memory (auto-detects language)
        transcription_result = await transcribe_audio(audio_data, filename=audio_file.filename or "audio.mp3", fast_mode=True)

        if "error" in transcription_result:
            return JSONResponse(
                status_code=500,
                content={"error": transcription_result["error"]}
            )

        transcribed_text = transcription_result["text"]
        detected_language = transcription_result.get("language", "unknown")

        if not transcribed_text.strip():
            return JSONResponse(
                status_code=400,
                content={"error": "No speech detected in the audio"}
            )

        logger.info(f"Transcription successful: '{transcribed_text}' (language: {detected_language})")

        return JSONResponse(
            status_code=200,
            content={
                "transcribed_text": transcribed_text,
                "detected_language": detected_language
            }
        )

    except Exception as e:
        logger.error(f"Error processing audio file: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Audio processing failed: {str(e)}"}
        )

@app.get("/conversation-history/{session_id}")
async def get_conversation_history(session_id: str):
    """Get conversation history for a session"""
    cleanup_expired_sessions()
    
    if session_id not in CONVERSATION_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = CONVERSATION_SESSIONS[session_id]
    if session.is_expired():
        del CONVERSATION_SESSIONS[session_id]
        raise HTTPException(status_code=404, detail="Session expired")
    
    return {
        "session_id": session_id,
        "chat_history": session.chat_history,
        "created_at": session.created_at.isoformat(),
        "last_activity": session.last_activity.isoformat()
    }

@app.post("/reset-conversation/{session_id}")
async def reset_conversation(session_id: str):
    """Reset conversation history for a session"""
    if session_id in CONVERSATION_SESSIONS:
        del CONVERSATION_SESSIONS[session_id]

    return {"message": "Conversation reset successfully", "session_id": session_id}

@app.get("/session/timeout")
async def get_session_timeout():
    """Get current session timeout configuration"""
    return {
        "current_timeout_seconds": int(SESSION_TIMEOUT.total_seconds()),
        "message": "Current session timeout configuration"
    }

class TimeoutRequest(BaseModel):
    timeout_seconds: int

@app.post("/session/timeout")
async def set_session_timeout(request: TimeoutRequest):
    """Set session timeout dynamically"""
    global SESSION_TIMEOUT

    # Validate timeout range (10 seconds to 1 hour)
    if request.timeout_seconds < 10:
        raise HTTPException(status_code=400, detail="Timeout must be at least 10 seconds")
    if request.timeout_seconds > 3600:
        raise HTTPException(status_code=400, detail="Timeout cannot exceed 3600 seconds (1 hour)")

    previous_timeout = int(SESSION_TIMEOUT.total_seconds())
    SESSION_TIMEOUT = timedelta(seconds=request.timeout_seconds)

    logger.info(f"Session timeout updated from {previous_timeout}s to {request.timeout_seconds}s")

    return {
        "message": "Session timeout updated successfully",
        "previous_timeout_seconds": previous_timeout,
        "new_timeout_seconds": request.timeout_seconds
    }

# --- Appointments Endpoints ---
@app.get("/appointments")
async def list_appointments():
    """Return all appointments. Protected by API key (checked in middleware)."""
    appointments = get_all_appointments()
    return {"appointments": appointments}


class AppointmentStatusUpdate(BaseModel):
    status: str


@app.put("/appointments/{appointment_id}/status")
async def update_status(appointment_id: str, body: AppointmentStatusUpdate):
    """Update the status of an appointment. Protected by API key (checked in middleware)."""
    valid_statuses = ["confirmed", "completed", "cancelled", "no-show"]
    if body.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    update_appointment_status(appointment_id, body.status)
    if body.status in ("cancelled", "no-show"):
        cancel_reminders(appointment_id)
    return {"success": True, "appointment_id": appointment_id, "status": body.status}


# --- Root Endpoint ---
@app.get("/")
async def read_root():
    return {
        "message": "Welcome to the Car Command AI API",
        "version": "1.0.0",
        "authentication": "API key required for all endpoints except this one",
        "endpoints": {
            "/process-command-unified/": "Process car commands (text or audio) (POST) - Requires API key",
            "/process-command/": "Process text commands (POST) - Requires API key",
            "/transcribe-audio/": "Transcribe audio to text only (POST) - Requires API key",
            "/conversation-history/{session_id}": "Get conversation history (GET) - Requires API key",
            "/reset-conversation/{session_id}": "Reset conversation history (POST) - Requires API key",
            "/session/timeout": "Get/Set session timeout (GET/POST) - Requires API key",
            "/transcription/info/": "Get transcription service info (GET) - Requires API key",
            "/auth/verify": "Verify API key (GET) - Requires API key"
        },
        "authentication_methods": [
            "Header: X-API-Key: <your-api-key>",
            "Header: Authorization: Bearer <your-api-key>"
        ]
    }

# --- API Key Verification Endpoint ---
@app.get("/auth/verify")
async def verify_api_key_endpoint():
    """Endpoint to verify if API key is valid - will only be reached if API key is valid"""
    return {
        "status": "success",
        "message": "API key is valid",
        "authenticated": True
    }

# --- Main Entry Point for Uvicorn (Keep as is) ---
if __name__ == "__main__":
    logger.info("Starting Car Command AI API with Uvicorn...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")