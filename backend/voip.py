import os
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Form
from fastapi.responses import Response

import google.generativeai as genai
from appointments_db import save_appointment
from reminders import schedule_reminders

logger = logging.getLogger(__name__)

# --- Twilio imports (graceful if not installed) ---
try:
    from twilio.twiml.voice_response import VoiceResponse, Gather
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    logger.warning("twilio package not installed. VoIP endpoints will return stub responses.")

# --- Configuration ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "models/gemini-2.5-flash-lite"

# In-memory session store: call_sid -> {state, collected, transcript}
voip_sessions: dict = {}

# States in order
STATES = ["greeting", "name", "phone", "email", "vehicle", "service", "date", "time", "confirming", "done"]

router = APIRouter(prefix="/voip")


def get_twilio_client():
    if TWILIO_AVAILABLE and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
        return TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    return None


def make_twiml_gather(prompt_text: str, action_url: str) -> str:
    if not TWILIO_AVAILABLE:
        return "<Response><Say>VoIP not configured.</Say></Response>"
    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action=action_url,
        method="POST",
        language="en-US",
        speech_timeout="auto",
    )
    gather.say(prompt_text, voice="Polly.Joanna")
    response.append(gather)
    response.say("We did not receive any input. Goodbye.", voice="Polly.Joanna")
    return str(response)


def make_twiml_say(message: str) -> str:
    if not TWILIO_AVAILABLE:
        return "<Response><Say>VoIP not configured.</Say></Response>"
    response = VoiceResponse()
    response.say(message, voice="Polly.Joanna")
    return str(response)


async def process_voip_speech(speech: str, session: dict) -> dict:
    """Use Gemini to extract info and advance the conversation state."""
    state = session.get("state", "greeting")
    collected = session.get("collected", {})
    transcript = session.get("transcript", [])

    prompt = """You are Sarah, a friendly car service appointment scheduling assistant for ABC Car Service Center.
You are conducting a phone call to schedule a car service appointment.

Current state: {state}
Information collected so far: {collected}
Recent transcript: {transcript}
Customer just said: "{speech}"

States in order: greeting -> name -> phone -> email -> vehicle -> service -> date -> time -> confirming -> done

- greeting  : welcome, ask for name
- name      : collect name, ask for phone number
- phone     : collect phone, ask for email address
- email     : collect email, ask for vehicle (make, model, year)
- vehicle   : collect vehicle info, ask what service they need
- service   : collect service type (oil change, brake inspection, etc.), ask preferred date
- date      : collect date, ask preferred time (remind hours 8 AM to 5 PM, Mon-Sat)
- time      : collect time, read back ALL details and ask customer to confirm
- confirming: if customer says yes/correct/confirm → set save_appointment=true and next_state=done
              if customer wants a change → ask what to change and go back to the relevant state
- done      : say a warm goodbye with appointment ID placeholder

Respond ONLY with valid JSON in this exact format:
{{
  "extracted": {{
    "name": null,
    "phone": null,
    "email": null,
    "vehicle": null,
    "service_type": null,
    "appointment_date": null,
    "appointment_time": null
  }},
  "reply": "what to say to the customer",
  "next_state": "next state name",
  "save_appointment": false
}}

Only set save_appointment=true when in confirming state AND customer has confirmed all details.
Only include fields in extracted that were actually mentioned in this turn (use null for others).
Keep replies concise and conversational (2-3 sentences). Be warm and professional.
""".format(
        state=state,
        collected=json.dumps(collected),
        transcript=json.dumps(transcript[-10:]),
        speech=speech,
    )

    try:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not set")
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(MODEL_NAME)
        result = model.generate_content(prompt)
        raw = result.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Gemini non-JSON response: {e}")
    except Exception as e:
        logger.error(f"process_voip_speech error: {e}")

    return {
        "extracted": {},
        "reply": "I'm sorry, I had a technical issue. Could you please repeat that?",
        "next_state": state,
        "save_appointment": False,
    }


def send_confirmation(phone: str, email: str, appointment_data: dict, appointment_id: str):
    """Send SMS + email confirmation immediately after booking."""
    name = appointment_data.get("name", "Customer")
    vehicle = appointment_data.get("vehicle", "your vehicle")
    service = appointment_data.get("service_type", "service")
    date = appointment_data.get("appointment_date", "")
    time = appointment_data.get("appointment_time", "")

    # --- SMS ---
    client = get_twilio_client()
    if client and TWILIO_PHONE_NUMBER and phone:
        try:
            sms_body = (
                f"Hi {name}! Your {service} appointment for {vehicle} "
                f"is confirmed for {date} at {time}. "
                f"Ref: {appointment_id[:8]}. "
                f"You'll receive reminders 24h, 3h, and 1h before. "
                f"- ABC Car Service Center"
            )
            client.messages.create(body=sms_body, from_=TWILIO_PHONE_NUMBER, to=phone)
            logger.info(f"Confirmation SMS sent to {phone}")
        except Exception as e:
            logger.error(f"SMS confirmation failed: {e}")

    # --- Email (AWS SES) ---
    if email:
        try:
            import boto3
            from reminders import SES_SENDER_EMAIL, AWS_REGION
            if not SES_SENDER_EMAIL:
                logger.warning("SES_SENDER_EMAIL not set — email confirmation skipped.")
                return
            ses = boto3.client("ses", region_name=AWS_REGION)
            subject = "Your ABC Car Service Appointment is Confirmed"
            body_text = (
                f"Dear {name},\n\n"
                f"Your service appointment has been confirmed!\n\n"
                f"  Vehicle : {vehicle}\n"
                f"  Service : {service}\n"
                f"  Date    : {date}\n"
                f"  Time    : {time}\n"
                f"  Ref     : {appointment_id}\n\n"
                f"You will receive reminder notifications 24 hours, 3 hours, and 1 hour before your appointment.\n\n"
                f"ABC Car Service Center"
            )
            body_html = f"""
            <html><body style="font-family:Arial,sans-serif;color:#333;">
              <h2 style="color:#2c3e50;">Appointment Confirmed!</h2>
              <p>Dear <strong>{name}</strong>,</p>
              <p>Your Toyota service appointment is confirmed:</p>
              <table style="border-collapse:collapse;width:100%;max-width:480px;">
                <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5;"><strong>Vehicle</strong></td>
                    <td style="padding:8px;border:1px solid #ddd;">{vehicle}</td></tr>
                <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5;"><strong>Service</strong></td>
                    <td style="padding:8px;border:1px solid #ddd;">{service}</td></tr>
                <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5;"><strong>Date</strong></td>
                    <td style="padding:8px;border:1px solid #ddd;">{date}</td></tr>
                <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5;"><strong>Time</strong></td>
                    <td style="padding:8px;border:1px solid #ddd;">{time}</td></tr>
              </table>
              <p style="margin-top:16px;">
                You will receive reminders <strong>24 hours</strong>, <strong>3 hours</strong>,
                and <strong>1 hour</strong> before your appointment.
              </p>
              <p style="font-size:12px;color:#888;">Reference: {appointment_id}</p>
              <p>— ABC Car Service Center</p>
            </body></html>
            """
            ses.send_email(
                Source=SES_SENDER_EMAIL,
                Destination={"ToAddresses": [email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": body_text, "Charset": "UTF-8"},
                        "Html": {"Data": body_html, "Charset": "UTF-8"},
                    },
                },
            )
            logger.info(f"Confirmation email sent to {email}")
        except Exception as e:
            logger.error(f"Email confirmation failed: {e}")


@router.post("/incoming-call")
async def incoming_call(
    CallSid: str = Form(default=None),
    From: str = Form(default=None),
):
    call_sid = CallSid or "unknown"
    logger.info(f"Incoming VoIP call: CallSid={call_sid}, From={From}")

    voip_sessions[call_sid] = {
        "state": "name",
        "collected": {"phone": From} if From else {},
        "transcript": [],
    }

    greeting = (
        "Thank you for calling ABC Car Service Center. "
        "I'm Sarah, your virtual assistant, and I'll help you schedule a car service appointment today. "
        "May I have your full name please?"
    )

    twiml = make_twiml_gather(prompt_text=greeting, action_url="/voip/gather")
    return Response(content=twiml, media_type="application/xml")


@router.post("/gather")
async def gather(
    CallSid: str = Form(default=None),
    SpeechResult: str = Form(default=None),
    Confidence: str = Form(default=None),
):
    call_sid = CallSid or "unknown"
    speech = SpeechResult or ""

    logger.info(f"Gather: CallSid={call_sid}, Speech='{speech}'")

    if call_sid not in voip_sessions:
        voip_sessions[call_sid] = {"state": "name", "collected": {}, "transcript": []}

    session = voip_sessions[call_sid]

    if not speech.strip():
        twiml = make_twiml_gather(
            prompt_text="I'm sorry, I didn't catch that. Could you please repeat?",
            action_url="/voip/gather",
        )
        return Response(content=twiml, media_type="application/xml")

    session["transcript"].append({"role": "customer", "text": speech})

    result = await process_voip_speech(speech, session)

    # Merge extracted data
    extracted = result.get("extracted", {})
    for key, value in extracted.items():
        if value is not None:
            session["collected"][key] = value

    reply = result.get("reply", "Could you please repeat that?")
    next_state = result.get("next_state", session["state"])
    should_save = result.get("save_appointment", False)

    session["state"] = next_state

    if should_save:
        try:
            appointment_data = {
                **session["collected"],
                "call_sid": call_sid,
                "created_at": datetime.now().isoformat(),
                "status": "confirmed",
                "notes": f"Scheduled via VoIP call. CallSid: {call_sid}",
            }
            appointment_id = save_appointment(appointment_data)
            session["state"] = "done"
            logger.info(f"Appointment saved via VoIP: id={appointment_id}")

            phone = session["collected"].get("phone", "")
            email = session["collected"].get("email", "")

            # Immediate confirmation (SMS + email)
            send_confirmation(phone, email, appointment_data, appointment_id)

            # Schedule 24hr / 3hr / 1hr reminders
            schedule_reminders({**appointment_data, "appointment_id": appointment_id})

            reply = reply.replace("{appointment_id}", appointment_id[:8])

        except Exception as e:
            logger.error(f"Error saving VoIP appointment: {e}")
            reply += " However, there was an issue saving your appointment. Please call back to confirm."

    session["transcript"].append({"role": "assistant", "text": reply})

    if session["state"] == "done":
        twiml = make_twiml_say(reply)
        voip_sessions.pop(call_sid, None)
        return Response(content=twiml, media_type="application/xml")

    twiml = make_twiml_gather(prompt_text=reply, action_url="/voip/gather")
    return Response(content=twiml, media_type="application/xml")
