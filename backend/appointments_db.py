import os
import uuid
import logging
from datetime import datetime

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

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
