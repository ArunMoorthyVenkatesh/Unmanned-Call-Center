"""
Reminder system for car service appointments.
Sends SMS (Twilio) + Email (SMTP) reminders at:
  - 24 hours before
  - 3 hours before
  - 1 hour before
"""
import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore

logger = logging.getLogger(__name__)

# --- Twilio ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# --- SMTP Email ---
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# Keep for backward compat
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
SES_SENDER_EMAIL = SMTP_USER

REMINDER_OFFSETS = {
    "24hr": timedelta(hours=24),
    "3hr": timedelta(hours=3),
    "1hr": timedelta(hours=1),
}

# Singleton scheduler
_scheduler = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        jobstores = {"default": MemoryJobStore()}
        _scheduler = BackgroundScheduler(jobstores=jobstores, timezone="Asia/Bangkok")
    return _scheduler


def start_scheduler():
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("Reminder scheduler started.")


def stop_scheduler():
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Reminder scheduler stopped.")


# ---------------------------------------------------------------------------
# SMS helpers
# ---------------------------------------------------------------------------

def _send_sms(to_phone: str, body: str):
    if to_phone and not to_phone.startswith("+"):
        to_phone = "+65" + to_phone.lstrip("0")
    try:
        from twilio.rest import Client
        if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
            logger.warning("Twilio credentials not configured — SMS skipped.")
            return
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(body=body, from_=TWILIO_PHONE_NUMBER, to=to_phone)
        logger.info(f"SMS sent to {to_phone}")
    except Exception as e:
        logger.error(f"SMS send failed to {to_phone}: {e}")


# ---------------------------------------------------------------------------
# Email helpers (SMTP)
# ---------------------------------------------------------------------------

def _send_email(to_email: str, subject: str, body_text: str, body_html: str = None):
    try:
        if not SMTP_USER or not SMTP_PASSWORD:
            logger.warning("SMTP_USER/SMTP_PASSWORD not configured — email skipped.")
            return
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg.as_string())
        logger.info(f"Email sent to {to_email}: {subject}")
    except Exception as e:
        logger.error(f"Email send failed to {to_email}: {e}")


# ---------------------------------------------------------------------------
# Reminder job
# ---------------------------------------------------------------------------

def _send_reminder(
    appointment_id: str,
    name: str,
    phone: str,
    email: str,
    vehicle: str,
    service_type: str,
    appointment_date: str,
    appointment_time: str,
    label: str,
):
    """Job executed by APScheduler to send a reminder."""
    logger.info(f"Sending {label} reminder for appointment {appointment_id}")

    sms_body = (
        f"Reminder ({label}): Hi {name}, your {service_type} for {vehicle} "
        f"is on {appointment_date} at {appointment_time}. "
        f"ABC Car Service Center. Reply CANCEL to cancel."
    )
    email_subject = f"Reminder: Your Toyota Service Appointment in {label}"
    email_text = (
        f"Dear {name},\n\n"
        f"This is a reminder that your car service appointment is coming up:\n\n"
        f"  Vehicle : {vehicle}\n"
        f"  Service : {service_type}\n"
        f"  Date    : {appointment_date}\n"
        f"  Time    : {appointment_time}\n\n"
        f"Appointment ID: {appointment_id}\n\n"
        f"If you need to cancel or reschedule, please call us.\n\n"
        f"ABC Car Service Center"
    )
    email_html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;">
      <h2 style="color:#2c3e50;">Service Appointment Reminder</h2>
      <p>Dear <strong>{name}</strong>,</p>
      <p>Your car service appointment is coming up in <strong>{label}</strong>:</p>
      <table style="border-collapse:collapse;width:100%;max-width:480px;">
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5;"><strong>Vehicle</strong></td>
            <td style="padding:8px;border:1px solid #ddd;">{vehicle}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5;"><strong>Service</strong></td>
            <td style="padding:8px;border:1px solid #ddd;">{service_type}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5;"><strong>Date</strong></td>
            <td style="padding:8px;border:1px solid #ddd;">{appointment_date}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd;background:#f5f5f5;"><strong>Time</strong></td>
            <td style="padding:8px;border:1px solid #ddd;">{appointment_time}</td></tr>
      </table>
      <p style="margin-top:16px;font-size:12px;color:#888;">Appointment ID: {appointment_id}</p>
      <p>If you need to cancel or reschedule, please call us.</p>
      <p>— ABC Car Service Center</p>
    </body></html>
    """

    if phone:
        _send_sms(phone, sms_body)
    if email:
        _send_email(email, email_subject, email_text, email_html)


# ---------------------------------------------------------------------------
# Schedule reminders for a new appointment
# ---------------------------------------------------------------------------

def schedule_reminders(appointment: dict):
    """
    Schedule SMS + email reminders at 24hr, 3hr, 1hr before the appointment.
    appointment must have: appointment_id, appointment_date, appointment_time,
                           name, phone, email, vehicle, service_type
    """
    apt_date = appointment.get("appointment_date", "")
    apt_time = appointment.get("appointment_time", "")

    if not apt_date or not apt_time:
        logger.warning(f"Missing date/time for appointment {appointment.get('appointment_id')} — reminders skipped.")
        return

    # Try to parse appointment datetime (accept multiple formats)
    apt_dt = None
    for fmt in (
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %I:%M %p",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M",
        "%B %d, %Y %H:%M",
        "%B %d %Y %H:%M",
    ):
        try:
            apt_dt = datetime.strptime(f"{apt_date} {apt_time}".strip(), fmt)
            break
        except ValueError:
            continue

    if apt_dt is None:
        logger.warning(
            f"Cannot parse datetime '{apt_date} {apt_time}' for appointment "
            f"{appointment.get('appointment_id')} — reminders skipped."
        )
        return

    scheduler = get_scheduler()
    appointment_id = appointment["appointment_id"]

    for label, offset in REMINDER_OFFSETS.items():
        run_at = apt_dt - offset
        if run_at <= datetime.now():
            logger.info(f"Skipping {label} reminder for {appointment_id} — time already passed.")
            continue

        job_id = f"reminder_{appointment_id}_{label}"
        scheduler.add_job(
            _send_reminder,
            trigger="date",
            run_date=run_at,
            id=job_id,
            replace_existing=True,
            kwargs={
                "appointment_id": appointment_id,
                "name": appointment.get("name", ""),
                "phone": appointment.get("phone", ""),
                "email": appointment.get("email", ""),
                "vehicle": appointment.get("vehicle", ""),
                "service_type": appointment.get("service_type", ""),
                "appointment_date": apt_date,
                "appointment_time": apt_time,
                "label": label,
            },
        )
        logger.info(f"Scheduled {label} reminder for appointment {appointment_id} at {run_at}")


def cancel_reminders(appointment_id: str):
    """Remove all scheduled reminders for an appointment (e.g. when cancelled)."""
    scheduler = get_scheduler()
    for label in REMINDER_OFFSETS:
        job_id = f"reminder_{appointment_id}_{label}"
        try:
            scheduler.remove_job(job_id)
            logger.info(f"Removed reminder job {job_id}")
        except Exception:
            pass  # job may not exist
