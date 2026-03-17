import os
import uuid
import re
import logging
from datetime import datetime

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

# All valid 30-min slots: 08:00–12:00 and 14:00–16:30 (lunch 12:30–14:00 blocked)
ALL_SLOTS = [
    "08:00", "08:30", "09:00", "09:30", "10:00", "10:30",
    "11:00", "11:30", "12:00",
    "14:00", "14:30", "15:00", "15:30", "16:00", "16:30",
]
MAX_APPOINTMENTS_PER_DAY = 10


def normalize_time(time_str: str) -> str:
    """Convert any time string to HH:MM (24h). Returns '' if unparseable."""
    if not time_str:
        return ""
    t = time_str.strip().upper()
    # Already HH:MM 24h
    m = re.match(r'^(\d{1,2}):(\d{2})$', t)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    # HH:MM AM/PM
    m = re.match(r'^(\d{1,2}):(\d{2})\s*(AM|PM)$', t)
    if m:
        h, mn, period = int(m.group(1)), m.group(2), m.group(3)
        if period == "PM" and h != 12:
            h += 12
        if period == "AM" and h == 12:
            h = 0
        return f"{h:02d}:{mn}"
    # H AM/PM (no minutes)
    m = re.match(r'^(\d{1,2})\s*(AM|PM)$', t)
    if m:
        h, period = int(m.group(1)), m.group(2)
        if period == "PM" and h != 12:
            h += 12
        if period == "AM" and h == 12:
            h = 0
        return f"{h:02d}:00"
    return ""

logger = logging.getLogger(__name__)

TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME", "CarServiceAppointments")
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")

_dynamodb = None
_table = None


def _get_table():
    global _dynamodb, _table
    if _table is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
        _table = _dynamodb.Table(TABLE_NAME)
    return _table


def init_db():
    """Create DynamoDB table if it does not exist."""
    try:
        dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
        existing = [t.name for t in dynamodb.tables.all()]
        if TABLE_NAME in existing:
            logger.info(f"DynamoDB table '{TABLE_NAME}' already exists.")
            return

        table = dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "appointment_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "appointment_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
        logger.info(f"DynamoDB table '{TABLE_NAME}' created successfully.")
    except ClientError as e:
        logger.error(f"Error initialising DynamoDB table: {e}")
        raise


def save_appointment(data: dict) -> str:
    """Save a new appointment. Returns the appointment_id (UUID string)."""
    try:
        table = _get_table()
        appointment_id = str(uuid.uuid4())
        item = {
            "appointment_id": appointment_id,
            "name": data.get("name", ""),
            "phone": data.get("phone", ""),
            "email": data.get("email", ""),
            "vehicle": data.get("vehicle", ""),
            "service_type": data.get("service_type", ""),
            "appointment_date": data.get("appointment_date", ""),
            "appointment_time": data.get("appointment_time", ""),
            "status": data.get("status", "confirmed"),
            "created_at": data.get("created_at", datetime.now().isoformat()),
            "call_sid": data.get("call_sid", ""),
            "notes": data.get("notes", ""),
        }
        table.put_item(Item=item)
        logger.info(f"Appointment saved: appointment_id={appointment_id}")
        return appointment_id
    except Exception as e:
        logger.error(f"Error saving appointment: {e}")
        raise


def get_all_appointments() -> list:
    """Return all appointments, newest first."""
    try:
        table = _get_table()
        response = table.scan()
        items = response.get("Items", [])
        # Handle pagination
        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return items
    except Exception as e:
        logger.error(f"Error fetching appointments: {e}")
        return []


def get_appointments_by_date(date_str: str) -> list:
    """Return all confirmed/pending appointments for a given date (dd/mm/yyyy)."""
    try:
        table = _get_table()
        response = table.scan(FilterExpression=Attr("appointment_date").eq(date_str))
        items = response.get("Items", [])
        while "LastEvaluatedKey" in response:
            response = table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"],
                FilterExpression=Attr("appointment_date").eq(date_str),
            )
            items.extend(response.get("Items", []))
        # Exclude cancelled/no_show
        return [i for i in items if i.get("status") not in ("cancelled", "no_show")]
    except Exception as e:
        logger.error(f"Error fetching appointments for date {date_str}: {e}")
        return []


def get_available_slots(date_str: str) -> list:
    """Return list of available HH:MM slots for a date. Empty list = fully booked."""
    booked = get_appointments_by_date(date_str)
    if len(booked) >= MAX_APPOINTMENTS_PER_DAY:
        return []
    booked_times = {normalize_time(a.get("appointment_time", "")) for a in booked}
    return [s for s in ALL_SLOTS if s not in booked_times]


def is_slot_available(date_str: str, time_str: str) -> bool:
    """Check if a specific slot is available."""
    normalized = normalize_time(time_str)
    if not normalized or normalized not in ALL_SLOTS:
        return False
    available = get_available_slots(date_str)
    return normalized in available


def get_appointment(appointment_id: str) -> dict:
    """Return a single appointment by ID, or None."""
    try:
        table = _get_table()
        response = table.get_item(Key={"appointment_id": appointment_id})
        return response.get("Item")
    except Exception as e:
        logger.error(f"Error fetching appointment {appointment_id}: {e}")
        return None


def update_appointment_status(appointment_id: str, status: str):
    """Update the status field of an appointment."""
    try:
        table = _get_table()
        table.update_item(
            Key={"appointment_id": appointment_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": status},
        )
        logger.info(f"Appointment {appointment_id} status → '{status}'")
    except Exception as e:
        logger.error(f"Error updating appointment status: {e}")
        raise


def get_confirmed_appointments_for_reminders() -> list:
    """Return all confirmed appointments (for reminder scheduling)."""
    try:
        table = _get_table()
        response = table.scan(
            FilterExpression=Attr("status").eq("confirmed")
        )
        items = response.get("Items", [])
        while "LastEvaluatedKey" in response:
            response = table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"],
                FilterExpression=Attr("status").eq("confirmed"),
            )
            items.extend(response.get("Items", []))
        return items
    except Exception as e:
        logger.error(f"Error fetching confirmed appointments: {e}")
        return []
