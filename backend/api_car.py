import os
import logging
import asyncio
import re
import json
from datetime import datetime, timezone
from typing import Optional # Import Optional
from serpapi import GoogleSearch
import random
import pandas as pd
import requests
import docx
from pathlib import Path
import pickle
import numpy as np
import tempfile
from groq import Groq

# Try to import numpy, but make it optional for VAD
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    print("Warning: numpy not available, VAD will use basic processing")

import google.generativeai as genai
from dotenv import load_dotenv
from voip import router as voip_router
from appointments_db import init_db, get_all_appointments, update_appointment_status
from reminders import start_scheduler, stop_scheduler, cancel_reminders

from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
from typing import List, Dict
import uuid
from datetime import datetime, timedelta
from geopy.distance import geodesic
import pdfplumber

# Voice Recognition Library
try:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")
    from voice_recognition_wrapper import VoiceRecognitionLibrary, STATUS_SUCCESS, STATUS_RESULT
    VOICE_RECOGNITION_AVAILABLE = True
    print("Voice Recognition Library loaded successfully")
except ImportError as e:
    print(f"Voice Recognition Library not available: {e}")
    VOICE_RECOGNITION_AVAILABLE = False

# --- Semantic Search Imports ---
try:
    from sentence_transformers import SentenceTransformer
    import faiss
    SEMANTIC_SEARCH_AVAILABLE = True
except ImportError:
    SEMANTIC_SEARCH_AVAILABLE = False
    logger.warning("Semantic search libraries not available. Install sentence-transformers and faiss-cpu for enhanced manual search.")

# --- Hugging Face Imports ---
# from transformers import AutoTokenizer, AutoModelForCausalLM # For GPT-like models
# Or for text-to-text models like T5:
# from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

# --- Configuration ---
load_dotenv()
init_db()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
API_KEY = "nUutfYzyfwDyQ99r-7eYkQULAQLpk95zKkhlp-ISmpM"

GROQ_CLIENT = None
TRANSCRIPTION_MODEL = "whisper-large-v3-turbo"

if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY must be set in your .env file.")

if not SERPAPI_API_KEY:
    print("Error: SERPAPI_API_KEY must be set in your .env file.")
    
CONVERSATION_SESSIONS = {}
SESSION_TIMEOUT = timedelta(seconds=300)

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BANGKOK_LOCATIONS = {
    "Siam": (13.7466, 100.5347),
    "Chatuchak": (13.8150, 100.5563),
    "Sathorn": (13.7212, 100.5287),
    "Bang Kapi": (13.7650, 100.6422),
    "Bang Na": (13.6682, 100.6075),
    "Phra Khanong": (13.7147, 100.5986),
    "Thonglor": (13.7300, 100.5765),
    "Lat Krabang": (13.7290, 100.7785),
    "Ratchada": (13.7765, 100.5734),
    "Victory Monument": (13.7655, 100.5382)
}
USER_LAT, USER_LON = random.choice(list(BANGKOK_LOCATIONS.values()))

# --- Lottery Configuration ---
LOTTERY_DATES = {}

def fetch_lottery_dates() -> dict:
    """Fetch available lottery dates from the real-time API."""
    try:
        url = "https://lotto.api.rayriffy.com/list/1"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "success" and "response" in data:
            lottery_dates = {}
            for item in data["response"]:
                date_id = item["id"]
                lottery_dates[date_id] = {
                    "url": item["url"],
                    "date": item["date"],
                    "id": date_id
                }

            logger.info(f"Fetched {len(lottery_dates)} lottery dates from API")
            return lottery_dates
        else:
            logger.error(f"Invalid API response structure: {data}")
            return {}

    except requests.RequestException as e:
        logger.error(f"Error fetching lottery dates from API: {e}")
        # Fallback to predefined dates if API fails
        return get_fallback_lottery_dates()
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing lottery dates JSON: {e}")
        return get_fallback_lottery_dates()

def get_fallback_lottery_dates() -> dict:
    """Fallback lottery dates in case the API is unavailable."""
    logger.warning("Using fallback lottery dates due to API failure")

    # Thai lottery is drawn twice a month: 1st and 16th
    lottery_dates = {
        "16092568": {"url": "/lotto/16092568", "date": "16 กันยายน 2568", "id": "16092568"},
        "01092568": {"url": "/lotto/01092568", "date": "1 กันยายน 2568", "id": "01092568"},
        "16082568": {"url": "/lotto/16082568", "date": "16 สิงหาคม 2568", "id": "16082568"},
        "01082568": {"url": "/lotto/01082568", "date": "1 สิงหาคม 2568", "id": "01082568"},
        "16072568": {"url": "/lotto/16072568", "date": "16 กรกฎาคม 2568", "id": "16072568"},
        "01072568": {"url": "/lotto/01072568", "date": "1 กรกฎาคม 2568", "id": "01072568"},
        "16062568": {"url": "/lotto/16062568", "date": "16 มิถุนายน 2568", "id": "16062568"},
        "01062568": {"url": "/lotto/01062568", "date": "1 มิถุนายน 2568", "id": "01062568"},
        "16052568": {"url": "/lotto/16052568", "date": "16 พฤษภาคม 2568", "id": "16052568"},
        "02052568": {"url": "/lotto/02052568", "date": "2 พฤษภาคม 2568", "id": "02052568"},
        "16042568": {"url": "/lotto/16042568", "date": "16 เมษายน 2568", "id": "16042568"},
        "01042568": {"url": "/lotto/01042568", "date": "1 เมษายน 2568", "id": "01042568"},
        "16032568": {"url": "/lotto/16032568", "date": "16 มีนาคม 2568", "id": "16032568"},
        "01032568": {"url": "/lotto/01032568", "date": "1 มีนาคม 2568", "id": "01032568"},
        "16022568": {"url": "/lotto/16022568", "date": "16 กุมภาพันธ์ 2568", "id": "16022568"},
        "01022568": {"url": "/lotto/01022568", "date": "1 กุมภาพันธ์ 2568", "id": "01022568"},
        "17012568": {"url": "/lotto/17012568", "date": "17 มกราคม 2568", "id": "17012568"},
        "02012568": {"url": "/lotto/02012568", "date": "2 มกราคม 2568", "id": "02012568"},
        "16122567": {"url": "/lotto/16122567", "date": "16 ธันวาคม 2567", "id": "16122567"},
        "01122567": {"url": "/lotto/01122567", "date": "1 ธันวาคม 2567", "id": "01122567"},
        "16112567": {"url": "/lotto/16112567", "date": "16 พฤศจิกายน 2567", "id": "16112567"}
    }

    return lottery_dates

def fetch_lottery_results(date_id: str) -> dict:
    """Fetch lottery results for a specific date ID."""
    try:
        url = f"https://lotto.api.rayriffy.com/lotto/{date_id}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        logger.info(f"Lottery API response for {date_id}: {data}")
        return data

    except requests.RequestException as e:
        logger.error(f"Error fetching lottery results for {date_id}: {e}")
        return {"error": f"Failed to fetch lottery results: {str(e)}"}
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing lottery results JSON for {date_id}: {e}")
        return {"error": f"Invalid lottery results format: {str(e)}"}

def get_latest_lottery_date() -> str:
    """Get the most recent lottery date ID that is not ahead of the current date.
    Uses Thai Buddhist Era calendar where 2567 = 2024, 2568 = 2025, etc."""
    from datetime import datetime
    global LOTTERY_DATES
    if not LOTTERY_DATES:
        LOTTERY_DATES = fetch_lottery_dates()

    if not LOTTERY_DATES:
        return None

    # Get current date in Thai Buddhist Era format (DDMMYYYY)
    current_date = datetime.now()
    current_thai_year = current_date.year + 543  # Convert to Buddhist Era
    current_date_id = f"{current_date.day:02d}{current_date.month:02d}{current_thai_year}"

    logger.info(f"Current date in Thai format: {current_date_id} (Gregorian: {current_date.strftime('%d/%m/%Y')})")

    # Find all dates that are not ahead of current date
    valid_dates = []

    for date_id in LOTTERY_DATES.keys():
        try:
            # Parse the date ID: DDMMYYYY
            day = int(date_id[:2])
            month = int(date_id[2:4])
            year = int(date_id[4:8])

            # Convert to comparable format for direct comparison
            # Compare as integers: YYYYMMDD format for easy comparison
            lottery_date_int = year * 10000 + month * 100 + day
            current_date_int = current_thai_year * 10000 + current_date.month * 100 + current_date.day

            # Only include dates that are not ahead of current date
            if lottery_date_int <= current_date_int:
                # Also convert to Gregorian for logging
                gregorian_year = year - 543
                gregorian_date = datetime(gregorian_year, month, day)
                valid_dates.append((date_id, lottery_date_int, gregorian_date))
                logger.debug(f"Valid date: {date_id} (Thai: {day:02d}/{month:02d}/{year}, Gregorian: {gregorian_date.strftime('%d/%m/%Y')})")
            else:
                logger.debug(f"Future date excluded: {date_id} (Thai: {day:02d}/{month:02d}/{year})")

        except (ValueError, IndexError) as e:
            logger.warning(f"Invalid date format: {date_id}, error: {e}")
            continue

    if not valid_dates:
        logger.warning("No valid dates found (all dates are in the future), using fallback")
        # If no valid dates found, return the first available date as fallback
        return list(LOTTERY_DATES.keys())[0]

    # Sort by Thai date (most recent first) and return the latest date ID
    valid_dates.sort(key=lambda x: x[1], reverse=True)
    latest_date_id = valid_dates[0][0]
    latest_gregorian_date = valid_dates[0][2]

    logger.info(f"Selected latest available lottery date: {latest_date_id} ({LOTTERY_DATES[latest_date_id]['date']}) - Gregorian: {latest_gregorian_date.strftime('%d/%m/%Y')}")
    return latest_date_id

def filter_lottery_results(results: dict, query: str = "") -> dict:
    """Filter lottery results to return only relevant prize information based on query.

    Optimized for speed - reduces data size by 80-90% by filtering unnecessary information.

    Args:
        results: Full lottery results from API
        query: User's query to determine what prizes to include

    Returns:
        Filtered results with only relevant prize information
    """
    if not results or 'response' in results and not results['response']:
        return results

    response_data = results.get('response', {})

    # Check if user is asking about a specific number
    import re
    numbers_in_query = re.findall(r'\d+', query.lower())
    user_number = numbers_in_query[0] if numbers_in_query else None

    # Determine what to include based on query
    query_lower = query.lower()
    is_general_query = not user_number and ('lottery' in query_lower or 'หวย' in query_lower or 'result' in query_lower)

    filtered_response = {}

    if is_general_query:
        # For general queries, ONLY include 1st prize
        if 'first' in response_data:
            filtered_response['first'] = response_data['first']
        logger.info("Lottery filter: General query - returning only 1st prize")
    elif user_number:
        # User checking specific number - include all prizes for matching
        filtered_response = response_data
        logger.info(f"Lottery filter: Checking number {user_number} - returning all prizes")
    else:
        # Default: include top prizes only (1st, 2-digit, 3-digit)
        for key in ['first', 'last2', 'last3f', 'last3b']:
            if key in response_data:
                filtered_response[key] = response_data[key]
        logger.info("Lottery filter: Default - returning top prizes only")

    # Keep metadata
    if 'date' in response_data:
        filtered_response['date'] = response_data['date']
    if 'endpoint' in response_data:
        filtered_response['endpoint'] = response_data['endpoint']

    return {'response': filtered_response}

def perform_lottery_search(query: str) -> dict:
    """Perform lottery search using the lottery API with intelligent result filtering."""
    global LOTTERY_DATES

    # Refresh lottery dates if not loaded
    if not LOTTERY_DATES:
        LOTTERY_DATES = fetch_lottery_dates()

    if not LOTTERY_DATES:
        return {"error": "Unable to fetch lottery dates from API"}

    # Get the latest available lottery date (not in the future)
    selected_date_id = get_latest_lottery_date()
    if not selected_date_id:
        return {"error": "No lottery dates available"}

    logger.info(f"Using latest available lottery date: {selected_date_id} ({LOTTERY_DATES[selected_date_id]['date']})")

    # Fetch the lottery results for the selected date
    results = fetch_lottery_results(selected_date_id)

    if "error" in results:
        return results

    # Check if results are available (not XXX)
    if results and isinstance(results, dict):
        # Check if the lottery has been drawn yet
        # The API structure may vary, but typically if results are "XXX" or similar, it means not drawn yet
        result_text = str(results)
        if "XXX" in result_text or "xxx" in result_text.lower():
            return {
                "lottery_status": "not_drawn",
                "date_info": LOTTERY_DATES.get(selected_date_id, {}),
                "message": "Lottery results have not been drawn yet for this date"
            }
        else:
            # Filter results to reduce data size and improve speed
            filtered_results = filter_lottery_results(results, query)
            return {
                "lottery_status": "available",
                "results": filtered_results,
                "date_info": LOTTERY_DATES.get(selected_date_id, {}),
                "date_id": selected_date_id
            }

    return {"error": "Invalid lottery results format"}

# --- Gemini Configuration (Keep as is) ---
MODEL_NAME_GEMINI = 'models/gemini-2.5-flash-lite'
MODEL_NAME_GEMINI_ROUTING = 'models/gemini-2.5-flash-lite'  # Fastest model for routing
gemini_model = None
gemini_routing_model = None  # Separate lightweight model for fast routing

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel(MODEL_NAME_GEMINI)
        logger.info(f"Gemini model '{MODEL_NAME_GEMINI}' initialized.")

        # Initialize separate routing model for speed
        gemini_routing_model = genai.GenerativeModel(MODEL_NAME_GEMINI_ROUTING)
        logger.info(f"Gemini routing model '{MODEL_NAME_GEMINI_ROUTING}' initialized for fast query routing.")
    except Exception as e:
        logger.error(f"Error initializing Gemini model '{MODEL_NAME_GEMINI}': {e}", exc_info=True)
        # raise # Don't raise if we want to allow HF to run even if Gemini fails

generation_config_gemini = genai.GenerationConfig(temperature=0.4, top_p=0.9, top_k=40)
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

# --- Hugging Face Model Configuration ---
# Choose a model. distilgpt2 is small. t5-small is good for text-to-text.
HF_MODEL_NAME = "distilgpt2"
# HF_MODEL_NAME = "t5-small" # Alternative

# hf_tokenizer = None
# hf_model = None

# async def load_huggingface_model():
#     global hf_tokenizer, hf_model
#     if hf_model is None or hf_tokenizer is None: # Load only once
#         logger.info(f"Loading Hugging Face model: {HF_MODEL_NAME}...")
#         try:
#             hf_tokenizer = AutoTokenizer.from_pretrained(HF_MODEL_NAME)
#             if "gpt" in HF_MODEL_NAME.lower(): # Causal LM like GPT2
#                 hf_model = AutoModelForCausalLM.from_pretrained(HF_MODEL_NAME)
#                 # GPT-2 models might not have a pad token, set it to eos_token
#                 if hf_tokenizer.pad_token is None:
#                     hf_tokenizer.pad_token = hf_tokenizer.eos_token
#             elif "t5" in HF_MODEL_NAME.lower(): # Seq2Seq LM like T5
#                  hf_model = AutoModelForSeq2SeqLM.from_pretrained(HF_MODEL_NAME)
#             else: # Fallback or other model types
#                 hf_model = AutoModelForCausalLM.from_pretrained(HF_MODEL_NAME) # Assuming Causal LM if not specified
#                 if hasattr(hf_tokenizer, 'pad_token') and hf_tokenizer.pad_token is None and hasattr(hf_tokenizer, 'eos_token'):
#                     hf_tokenizer.pad_token = hf_tokenizer.eos_token

#             logger.info(f"Hugging Face model '{HF_MODEL_NAME}' loaded successfully.")
#         except Exception as e:
#             logger.error(f"Error loading Hugging Face model '{HF_MODEL_NAME}': {e}", exc_info=True)
#             # Depending on your needs, you might want to exit or just log the error
#             # For now, we'll let the app start but the HF endpoint will fail.

# --- Car Data Loading Functions ---
CAR_DATA = {}
JOKES_DATA = {}
DEALERSHIPS_DATA = {}
CAR_SPECIFICATIONS = {}

# --- Semantic Search Variables ---
MANUAL_EMBEDDINGS = None
MANUAL_PAGES = []
EMBEDDING_MODEL = None
FAISS_INDEX = None

CAR_COMMANDS_DATA = ""

async def load_jokes_from_csv(file_path: str):
    """Load jokes from a CSV file into JOKES_DATA, separated by language"""
    global JOKES_DATA
    try:
        df = pd.read_csv(file_path)
        all_jokes = df['Joke'].dropna().tolist()

        # Separate jokes by language (Thai vs English)
        thai_jokes = []
        english_jokes = []

        for joke in all_jokes:
            # Check if joke contains Thai characters
            if any('\u0E00' <= char <= '\u0E7F' for char in joke):
                thai_jokes.append(joke)
            else:
                english_jokes.append(joke)

        JOKES_DATA['csv'] = all_jokes  # Keep all jokes for backward compatibility
        JOKES_DATA['thai'] = thai_jokes
        JOKES_DATA['english'] = english_jokes

        logger.info(f"Loaded {len(all_jokes)} jokes from CSV ({len(english_jokes)} English, {len(thai_jokes)} Thai)")
        return True
    except Exception as e:
        logger.error(f"Error loading jokes CSV file {file_path}: {e}")
        return False
    
async def load_dealerships_from_csv(file_path: str):
    global DEALERSHIPS_DATA
    try:
        # Read CSV with header on first line
        df = pd.read_csv(file_path)
        df.columns = df.columns.str.strip()

        expected_cols = ['Dealer Name Thai', 'Dealer Name Eng', 'Latitude', 'Longitude']
        if not all(col in df.columns for col in expected_cols):
            logger.error(f"Missing expected columns. Found: {list(df.columns)}")
            return False

        # Filter out rows with missing or invalid data
        df = df.dropna(subset=['Dealer Name Thai', 'Dealer Name Eng', 'Latitude', 'Longitude'])
        df = df[df['Dealer Name Thai'].str.strip() != '']

        # Convert latitude and longitude to numeric, handling any errors
        df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
        df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')

        # Remove rows with invalid coordinates
        df = df.dropna(subset=['Latitude', 'Longitude'])
        df = df[(df['Latitude'] != 0) & (df['Longitude'] != 0)]

        DEALERSHIPS_DATA['all'] = df.to_dict('records')

        logger.info(f"Loaded {len(df)} dealerships")
        return True
    except Exception as e:
        logger.error(f"Error loading dealerships CSV file {file_path}: {e}")
        return False

def get_nearest_dealerships(user_lat: float, user_lon: float, limit: int = 5) -> list:
    """Calculate and return nearest dealerships based on user's current location."""
    if 'all' not in DEALERSHIPS_DATA or not DEALERSHIPS_DATA['all']:
        return []

    dealerships = []
    for dealer in DEALERSHIPS_DATA['all']:
        dealer_copy = dealer.copy()
        dealer_lat = dealer_copy.get('Latitude')
        dealer_lon = dealer_copy.get('Longitude')

        if dealer_lat and dealer_lon:
            distance = geodesic((user_lat, user_lon), (dealer_lat, dealer_lon)).km
            dealer_copy['distance_km'] = distance
            dealerships.append(dealer_copy)

    # Sort by distance and return top N
    dealerships.sort(key=lambda x: x['distance_km'])
    return dealerships[:limit]

async def load_car_specifications_from_csv(file_path: str):
    """Load car specifications from CSV file"""
    global CAR_SPECIFICATIONS
    try:
        df = pd.read_csv(file_path)
        # Convert to dictionary for easy lookup
        specs_dict = {}
        for _, row in df.iterrows():
            feature = str(row['Feature']).strip()
            specification = str(row['Specification']).strip()
            if feature and feature != 'nan' and specification and specification != 'nan':
                specs_dict[feature.lower()] = {
                    'feature': feature,
                    'specification': specification
                }

        CAR_SPECIFICATIONS = specs_dict
        logger.info(f"Loaded {len(specs_dict)} car specifications from CSV")
        return True
    except Exception as e:
        logger.error(f"Error loading car specifications CSV file {file_path}: {e}")
        return False

async def load_car_commands_from_csv(file_path: str):
    """Load car commands from CSV file and format them for the prompt"""
    global CAR_COMMANDS_DATA
    try:
        # Read CSV with Command Code as string to preserve leading zeros
        df = pd.read_csv(file_path, dtype={'Command Code': str}, keep_default_na=False)
        # Ensure Command Code column is treated as string
        df['Command Code'] = df['Command Code'].astype(str)
        # Filter out empty rows
        df = df.dropna(subset=['Action'])
        df = df[df['Command Code'].str.strip() != '']
        df = df[df['Action'].astype(str).str.strip() != '']

        commands_text = "\n**AVAILABLE COMMANDS:**\n"
        commands_text += "You MUST strictly map the user's request to **ONLY ONE** of the commands listed below:\n\n"

        for _, row in df.iterrows():
            # Ensure command code is properly formatted with leading zeros (8 digits)
            command_code = str(row['Command Code']).strip()
            # Pad with leading zeros if needed to ensure 8 digits
            if command_code.isdigit():
                command_code = command_code.zfill(8)

            action = str(row['Action']).strip()
            detail = str(row['Detail']).strip() if pd.notna(row['Detail']) and str(row['Detail']).strip() else ""
            example = str(row['Example']).strip() if pd.notna(row['Example']) and str(row['Example']).strip() else ""

            # Format the command
            if detail and example and detail != 'nan' and example != 'nan':
                commands_text += f"{action} <{detail}>: {command_code}\n"
                commands_text += f'Reply: "Setting {detail} to {example}." (replace {example} with actual value)\n'
            elif detail and detail != 'nan':
                commands_text += f"{action} <{detail}>: {command_code}\n"
                commands_text += f'Reply: "{action} set to <{detail}>." (replace with actual value)\n'
            else:
                commands_text += f"{action}: {command_code}\n"
                commands_text += f'Reply: "{action} completed."\n'

        CAR_COMMANDS_DATA = commands_text
        logger.info(f"Loaded {len(df)} car commands from CSV")

        # Debug: Log a few sample command codes to verify formatting
        sample_commands = commands_text.split('\n')[:10]
        logger.debug("Sample command codes loaded:")
        for cmd in sample_commands:
            if ':' in cmd and any(char.isdigit() for char in cmd):
                logger.debug(f"  {cmd}")

        return True

    except Exception as e:
        logger.error(f"Error loading car commands CSV file {file_path}: {e}")
        return False

async def load_car_data_from_pdf(file_path: str):
    """Load full car specifications from PDF file into CAR_DATA"""
    global CAR_DATA
    try:
        full_text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text.strip() + "\n"
        CAR_DATA['pdf'] = full_text
        logger.info(f"Loaded car data from PDF: {len(full_text)} characters")
        return True
    except Exception as e:
        logger.error(f"Error loading PDF file {file_path}: {e}")
        return False

async def initialize_semantic_search():
    """Initialize the semantic search model and load embeddings if available"""
    global EMBEDDING_MODEL, SEMANTIC_SEARCH_AVAILABLE

    if not SEMANTIC_SEARCH_AVAILABLE:
        logger.warning("Semantic search libraries not available. Skipping initialization.")
        return False

    try:
        # Initialize the embedding model
        try:
            EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Semantic search model initialized successfully")
        except Exception as cuda_error:
            if "CUDA" in str(cuda_error):
                logger.warning(f"CUDA error during initialization: {cuda_error}")
                logger.info("Falling back to CPU for semantic model...")
                EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')
                logger.info("Semantic search model initialized successfully with CPU")
            else:
                raise cuda_error
        return True
    except Exception as e:
        logger.error(f"Error initializing semantic search model: {e}")
        SEMANTIC_SEARCH_AVAILABLE = False
        return False

async def load_car_manual_with_embeddings(file_path: str, force_rebuild: bool = False):
    """Load car manual and create embeddings for semantic search"""
    global MANUAL_EMBEDDINGS, MANUAL_PAGES, FAISS_INDEX, EMBEDDING_MODEL

    if not SEMANTIC_SEARCH_AVAILABLE or not EMBEDDING_MODEL:
        logger.warning("Semantic search not available. Falling back to basic PDF loading.")
        return await load_car_data_from_pdf(file_path)

    embeddings_cache_path = f"{file_path}.embeddings.pkl"
    pages_cache_path = f"{file_path}.pages.pkl"

    # Try to load cached embeddings first
    if not force_rebuild and Path(embeddings_cache_path).exists() and Path(pages_cache_path).exists():
        try:
            with open(embeddings_cache_path, 'rb') as f:
                MANUAL_EMBEDDINGS = pickle.load(f)
            with open(pages_cache_path, 'rb') as f:
                MANUAL_PAGES = pickle.load(f)

            # Create FAISS index
            FAISS_INDEX = faiss.IndexFlatIP(MANUAL_EMBEDDINGS.shape[1])
            FAISS_INDEX.add(MANUAL_EMBEDDINGS.astype('float32'))

            logger.info(f"Loaded cached embeddings for {len(MANUAL_PAGES)} pages")

            return True
        except Exception as e:
            logger.warning(f"Error loading cached embeddings: {e}. Rebuilding...")

    # Extract text from PDF page by page
    try:
        pages_text = []
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and text.strip():
                    # Clean and prepare text
                    cleaned_text = text.strip().replace('\n', ' ').replace('\r', ' ')
                    # Remove excessive whitespace
                    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
                    pages_text.append({
                        'page_num': i + 1,
                        'text': cleaned_text,
                        'char_count': len(cleaned_text)
                    })

        if not pages_text:
            logger.error("No text extracted from PDF")
            return False

        MANUAL_PAGES = pages_text
        logger.info(f"Extracted text from {len(pages_text)} pages")

        # Create embeddings
        texts_for_embedding = [page['text'] for page in pages_text]
        MANUAL_EMBEDDINGS = EMBEDDING_MODEL.encode(texts_for_embedding, convert_to_numpy=True)

        # Create FAISS index
        FAISS_INDEX = faiss.IndexFlatIP(MANUAL_EMBEDDINGS.shape[1])
        FAISS_INDEX.add(MANUAL_EMBEDDINGS.astype('float32'))

        # Cache the embeddings and pages
        try:
            with open(embeddings_cache_path, 'wb') as f:
                pickle.dump(MANUAL_EMBEDDINGS, f)
            with open(pages_cache_path, 'wb') as f:
                pickle.dump(MANUAL_PAGES, f)
            logger.info("Cached embeddings for future use")
        except Exception as e:
            logger.warning(f"Could not cache embeddings: {e}")

        logger.info(f"Successfully created embeddings for {len(pages_text)} pages")

        return True

    except Exception as e:
        logger.error(f"Error processing car manual: {e}")
        # If CUDA error, try to reinitialize with CPU
        if "CUDA" in str(e) and EMBEDDING_MODEL is not None and 'pages_text' in locals():
            try:
                logger.warning("CUDA error detected. Attempting to reinitialize semantic model with CPU...")
                try:
                    import torch
                    torch.cuda.empty_cache()  # Clear CUDA cache
                except:
                    pass 

                # Reinitialize with CPU
                EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')
                logger.info("Successfully reinitialized semantic model with CPU")

                # Retry processing with CPU
                texts_for_embedding = [page['text'] for page in pages_text]
                MANUAL_EMBEDDINGS = EMBEDDING_MODEL.encode(texts_for_embedding, convert_to_numpy=True)

                # Create FAISS index
                FAISS_INDEX = faiss.IndexFlatIP(MANUAL_EMBEDDINGS.shape[1])
                FAISS_INDEX.add(MANUAL_EMBEDDINGS.astype('float32'))

                MANUAL_PAGES = pages_text
                logger.info(f"Successfully processed {len(MANUAL_PAGES)} pages with CPU fallback")

                # Cache the embeddings and pages after CPU fallback
                try:
                    logger.info(f"Caching embeddings to {embeddings_cache_path}")
                    with open(embeddings_cache_path, 'wb') as f:
                        pickle.dump(MANUAL_EMBEDDINGS, f)
                    with open(pages_cache_path, 'wb') as f:
                        pickle.dump(MANUAL_PAGES, f)
                    logger.info(f"Successfully cached embeddings to {embeddings_cache_path} and pages to {pages_cache_path}")
                except Exception as cache_error:
                    logger.error(f"Failed to cache embeddings after CPU fallback: {cache_error}")

                return True

            except Exception as cpu_error:
                logger.error(f"CPU fallback also failed: {cpu_error}")
                EMBEDDING_MODEL = None
        return False

def search_relevant_manual_pages(query: str, top_k: int = 3, min_similarity: float = 0.4):
    """Search for the most relevant pages in the car manual based on the query

    Optimised for speed:
    - Reduced top_k from 5 to 3 (fewer pages to process)
    - Increased min_similarity from 0.3 to 0.4 (higher quality, fewer results)
    - Batch processing for faster embedding generation
    """
    global MANUAL_EMBEDDINGS, MANUAL_PAGES, FAISS_INDEX, EMBEDDING_MODEL

    if not SEMANTIC_SEARCH_AVAILABLE or not EMBEDDING_MODEL or FAISS_INDEX is None:
        logger.warning("Semantic search not available. Returning empty results.")
        return []

    if not MANUAL_PAGES:
        logger.warning("No manual pages loaded. Returning empty results.")
        return []

    try:
        # Create embedding for the query (optimized with show_progress_bar=False for speed)
        query_embedding = EMBEDDING_MODEL.encode([query], convert_to_numpy=True, show_progress_bar=False, batch_size=1)

        # Search for similar pages (reduced top_k for speed)
        similarities, indices = FAISS_INDEX.search(query_embedding.astype('float32'), min(top_k, len(MANUAL_PAGES)))

        relevant_pages = []
        for i, (similarity, idx) in enumerate(zip(similarities[0], indices[0])):
            if similarity >= min_similarity:
                page_info = MANUAL_PAGES[idx].copy()
                page_info['similarity_score'] = float(similarity)
                page_info['rank'] = i + 1
                relevant_pages.append(page_info)

        logger.info(f"Found {len(relevant_pages)} relevant pages for query: '{query}' (optimized search)")
        return relevant_pages

    except Exception as e:
        logger.error(f"Error searching manual pages: {e}")

        # If CUDA error, try to reinitialize with CPU and retry
        if "CUDA" in str(e):
            try:
                logger.warning("CUDA error in manual search. Attempting to reinitialize with CPU...")
                from sentence_transformers import SentenceTransformer
                EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')
                logger.info("Successfully reinitialized embedding model with CPU for search")

                # Retry the search with CPU model
                query_embedding = EMBEDDING_MODEL.encode([query], convert_to_numpy=True)
                similarities, indices = FAISS_INDEX.search(query_embedding.astype('float32'), min(top_k, len(MANUAL_PAGES)))

                relevant_pages = []
                for i, (similarity, idx) in enumerate(zip(similarities[0], indices[0])):
                    if similarity >= min_similarity:
                        page_info = MANUAL_PAGES[idx].copy()
                        page_info['similarity_score'] = float(similarity)
                        page_info['rank'] = i + 1
                        relevant_pages.append(page_info)

                logger.info(f"Found {len(relevant_pages)} relevant pages for query: '{query}' (CPU fallback)")
                return relevant_pages

            except Exception as cpu_error:
                logger.error(f"CPU fallback for manual search also failed: {cpu_error}")
                return []

        return []

def get_car_manual_context(query: str = "", search_phrases: list = None, max_pages: int = 2, max_chars_per_page: int = 1500):
    """Generate car manual context from the most relevant pages

    Optimized for speed:
    - Reduced max_pages from 3 to 2 (less content to process)
    - Reduced max_chars_per_page from 2000 to 1500 (faster token processing)
    - Uses optimized search with higher similarity threshold

    Args:
        query: Original user query (for display purposes)
        search_phrases: List of optimized search phrases for semantic search (if None, uses query)
        max_pages: Maximum number of pages to return (default: 2 for speed)
        max_chars_per_page: Maximum characters per page (default: 1500 for speed)
    """
    if not query and not search_phrases:
        # If no specific query, return a general overview from first few pages
        if MANUAL_PAGES:
            context = "\n**CAR MANUAL INFORMATION:**\n"
            for page in MANUAL_PAGES[:max_pages]:
                text = page['text'][:max_chars_per_page]
                context += f"\nPage {page['page_num']}:\n{text}\n"
            return context
        return "\n**CAR MANUAL INFORMATION:**\nNo manual data available.\n"

    # Use search phrases if provided, otherwise use the original query
    phrases_to_search = search_phrases if search_phrases else [query]

    # Collect relevant pages from all search phrases
    all_relevant_pages = {}  # Use dict to avoid duplicates (keyed by page_num)

    for phrase in phrases_to_search:
        if not phrase:
            continue
        logger.info(f"Searching manual with phrase: '{phrase}'")
        # Optimized: top_k=2 (reduced), uses higher min_similarity in search_relevant_manual_pages
        relevant_pages = search_relevant_manual_pages(phrase, top_k=2, min_similarity=0.4)

        for page in relevant_pages:
            page_num = page['page_num']
            # Keep the page with highest similarity score if duplicate
            if page_num not in all_relevant_pages or page['similarity_score'] > all_relevant_pages[page_num]['similarity_score']:
                all_relevant_pages[page_num] = page

    # Convert dict back to list and sort by similarity score
    relevant_pages = sorted(all_relevant_pages.values(), key=lambda x: x['similarity_score'], reverse=True)[:max_pages]

    if not relevant_pages:
        # Fallback to basic search in existing CAR_DATA if available
        if 'pdf' in CAR_DATA:
            return f"\n**CAR MANUAL INFORMATION:**\n{CAR_DATA['pdf'][:max_chars_per_page * max_pages]}\n"
        return "\n**CAR MANUAL INFORMATION:**\nNo relevant manual information found.\n"

    search_info = f"'{query}'" if query else f"search phrases: {search_phrases}"
    context = f"\n**CAR MANUAL INFORMATION (Most relevant to: {search_info}):**\n"
    for page in relevant_pages:
        text = page['text'][:max_chars_per_page]
        similarity = page['similarity_score']
        context += f"\nPage {page['page_num']} (relevance: {similarity:.2f}):\n{text}\n"

    logger.info(f"Retrieved {len(relevant_pages)} manual pages (optimized for speed)")
    return context

def get_car_specifications_context(query: str = "", search_phrases: list = None):
    """Generate car specifications context from loaded manual data, with intelligent manual search

    Args:
        query: Original user query
        search_phrases: List of optimized search phrases from routing (if None, uses query)
    """
    # Use intelligent manual search if available, otherwise fall back to basic PDF
    if SEMANTIC_SEARCH_AVAILABLE and MANUAL_PAGES:
        return get_car_manual_context(query, search_phrases=search_phrases, max_pages=3, max_chars_per_page=1500)
    elif 'pdf' in CAR_DATA:
        context = "\n**CAR MANUAL INFORMATION:**\n"
        context += CAR_DATA['pdf'][:4500]  # Limit to avoid token overflow
        return context
    else:
        return "\n**CAR MANUAL INFORMATION:**\nNo car manual data available. Please ensure car_manual.pdf is loaded.\n"

def get_jokes(lang: str = "en"):
    """Generate joke context from loaded joke data, filtered by language

    Args:
        lang: Language choice - "en" for English, "th" for Thai
    """
    context = "\n**LIST OF JOKES:**\n"

    if 'csv' in JOKES_DATA:
        # Select jokes based on language
        if lang == "th" and 'thai' in JOKES_DATA:
            jokes_to_use = JOKES_DATA['thai']
            context += "Thai Jokes:\n"
        elif lang == "en" and 'english' in JOKES_DATA:
            jokes_to_use = JOKES_DATA['english']
            context += "English Jokes:\n"
        else:
            # Fallback to all jokes if language-specific not available
            jokes_to_use = JOKES_DATA['csv']
            context += "CSV Jokes:\n"

        for i, joke in enumerate(jokes_to_use[:15], start=1):
            context += f"{i}. {joke}\n"

    if 'docx' in JOKES_DATA:
        context += "\nDOCX Jokes (Paragraphs):\n"
        for i, paragraph in enumerate(JOKES_DATA['docx']['paragraphs'][:15], start=1):
            context += f"{i}. {paragraph}\n"

        if JOKES_DATA['docx']['tables']:
            context += "\nDOCX Jokes (Tables):\n"
            for t_index, table in enumerate(JOKES_DATA['docx']['tables'][:2], start=1):
                context += f"Table {t_index}:\n"
                for row in table[:5]:
                    context += f"  {' | '.join(row)}\n"

    return context

def perform_weather_search(lat: float, lon: float, units: str = "metric", lang: str = "en") -> dict:
    """Call OpenWeather One Call API 2.5 and return the parsed current weather info."""
    if not WEATHER_API_KEY:
        logger.error("Missing OpenWeather API key.")
        return {"error": "MISSING_WEATHER_API_KEY"}

    url = (
        f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&exclude=hourly,daily&units={units}&lang={lang}&appid={WEATHER_API_KEY}"
    )

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        weather_info = {
            "temperature": data.get("main", {}).get("temp"),
            "feels_like": data.get("main", {}).get("feels_like"),
            "humidity": data.get("main", {}).get("humidity"),
            "pressure": data.get("main", {}).get("pressure"),
            "wind_speed": data.get("wind", {}).get("speed"),
            "description": data.get("weather", [{}])[0].get("description"),
            "icon": data.get("weather", [{}])[0].get("icon"),
            "clouds": data.get("clouds", {}).get("all"),
            "dt": data.get("dt"),
            "sunrise": data.get("sys", {}).get("sunrise"),
            "sunset": data.get("sys", {}).get("sunset"),
            "location_name": data.get("name"),
        }

        return {
            "location": {
                "lat": data.get("coord", {}).get("lat"),
                "lon": data.get("coord", {}).get("lon"),
                "name": data.get("name"),
                "country": data.get("sys", {}).get("country")
            },
            "timezone_offset": data.get("timezone"),
            "weather": weather_info
        }

    except requests.RequestException as e:
        logger.error(f"Error calling OpenWeather API: {e}")
        return {"error": "WEATHER_API_CALL_FAILED", "details": str(e)}

def perform_hourly_forecast(lat: float, lon: float, units: str = "metric", lang: str = "en") -> dict:
    """Get hourly forecast for next 96 hours (4 days) using Hourly Forecast API (Pro subscription).

    Parameters:
        lat: Latitude
        lon: Longitude
        units: Units of measurement (standard, metric, imperial)
        lang: Language code
    """
    if not WEATHER_API_KEY:
        logger.error("Missing OpenWeather API key.")
        return {"error": "MISSING_WEATHER_API_KEY"}

    # Hourly Forecast API endpoint (requires Pro subscription)
    # Returns up to 96 hours (4 days) of hourly forecast
    url = f"https://pro.openweathermap.org/data/2.5/forecast/hourly?lat={lat}&lon={lon}&units={units}&lang={lang}&appid={WEATHER_API_KEY}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        logger.info(f"Hourly Forecast API response: cnt={data.get('cnt', 0)}, list_length={len(data.get('list', []))}")

        return {
            "location": {
                "lat": lat,
                "lon": lon,
                "city": data.get("city", {})
            },
            "cnt": data.get("cnt", 0),
            "list": data.get("list", [])  # Hourly forecast list
        }
    except requests.RequestException as e:
        logger.error(f"Error calling OpenWeather Hourly Forecast API: {e}")
        return {"error": "HOURLY_FORECAST_FAILED", "details": str(e)}

def perform_daily_forecast(lat: float, lon: float, days: int = 7, units: str = "metric", lang: str = "en") -> dict:
    """Get daily forecast for up to 16 days using Daily Forecast API.

    Parameters:
        lat: Latitude
        lon: Longitude
        days: Number of days (1-16)
        units: Units of measurement (standard, metric, imperial)
        lang: Language code
    """
    if not WEATHER_API_KEY:
        logger.error("Missing OpenWeather API key.")
        return {"error": "MISSING_WEATHER_API_KEY"}

    # Limit to 16 days max (API limit), minimum 1 day
    cnt = min(max(days, 1), 16)

    # Daily Forecast API endpoint with cnt parameter
    url = f"https://api.openweathermap.org/data/2.5/forecast/daily?lat={lat}&lon={lon}&cnt={cnt}&units={units}&lang={lang}&appid={WEATHER_API_KEY}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        logger.info(f"Daily Forecast API response: cnt={data.get('cnt', 0)}, list_length={len(data.get('list', []))}")

        return {
            "location": {
                "lat": lat,
                "lon": lon,
                "city": data.get("city", {})
            },
            "cnt": data.get("cnt", 0),
            "list": data.get("list", [])  # Daily forecast list
        }
    except requests.RequestException as e:
        logger.error(f"Error calling OpenWeather Daily Forecast API: {e}")
        return {"error": "DAILY_FORECAST_FAILED", "details": str(e)}

def perform_air_pollution_current(lat: float, lon: float) -> dict:
    """Get current air pollution data."""
    if not WEATHER_API_KEY:
        logger.error("Missing OpenWeather API key.")
        return {"error": "MISSING_WEATHER_API_KEY"}

    url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        logger.info(f"Air Pollution API response: list_length={len(data.get('list', []))}")

        return {
            "location": {"lat": lat, "lon": lon},
            "air_quality": data.get("list", [{}])[0] if data.get("list") else {}
        }
    except requests.RequestException as e:
        logger.error(f"Error calling OpenWeather Air Pollution API: {e}")
        return {"error": "AIR_POLLUTION_FAILED", "details": str(e)}

def perform_air_pollution_forecast(lat: float, lon: float) -> dict:
    """Get air pollution forecast.

    Returns data in format matching OpenWeather API response:
    {
        "coord": [lat, lon],
        "list": [
            {
                "dt": timestamp,
                "main": {"aqi": 1-5},
                "components": {"co": ..., "no": ..., "no2": ..., "o3": ..., "so2": ..., "pm2_5": ..., "pm10": ..., "nh3": ...}
            }
        ]
    }
    """
    if not WEATHER_API_KEY:
        logger.error("Missing OpenWeather API key.")
        return {"error": "MISSING_WEATHER_API_KEY"}

    url = f"http://api.openweathermap.org/data/2.5/air_pollution/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        logger.info(f"Air Pollution Forecast API response: list_length={len(data.get('list', []))}")

        # Return in the same format as the API response
        return {
            "location": {"lat": lat, "lon": lon},
            "coord": data.get("coord", [lat, lon]),
            "list": data.get("list", []),
            "is_forecast": True  # Flag to identify this as forecast data
        }
    except requests.RequestException as e:
        logger.error(f"Error calling OpenWeather Air Pollution Forecast API: {e}")
        return {"error": "AIR_POLLUTION_FORECAST_FAILED", "details": str(e)}

def perform_air_pollution_historical(lat: float, lon: float, start: int, end: int) -> dict:
    """Get historical air pollution data.

    Args:
        lat: Latitude
        lon: Longitude
        start: Start date (Unix timestamp)
        end: End date (Unix timestamp)

    Returns data in format matching OpenWeather API response:
    {
        "coord": [lat, lon],
        "list": [
            {
                "dt": timestamp,
                "main": {"aqi": 1-5},
                "components": {"co": ..., "no": ..., "no2": ..., "o3": ..., "so2": ..., "pm2_5": ..., "pm10": ..., "nh3": ...}
            }
        ]
    }
    """
    if not WEATHER_API_KEY:
        logger.error("Missing OpenWeather API key.")
        return {"error": "MISSING_WEATHER_API_KEY"}

    url = f"http://api.openweathermap.org/data/2.5/air_pollution/history?lat={lat}&lon={lon}&start={start}&end={end}&appid={WEATHER_API_KEY}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        logger.info(f"Air Pollution Historical API response: list_length={len(data.get('list', []))}")

        # Return in the same format as the API response
        return {
            "location": {"lat": lat, "lon": lon},
            "coord": data.get("coord", [lat, lon]),
            "list": data.get("list", []),
            "is_historical": True  # Flag to identify this as historical data
        }
    except requests.RequestException as e:
        logger.error(f"Error calling OpenWeather Air Pollution Historical API: {e}")
        return {"error": "AIR_POLLUTION_HISTORICAL_FAILED", "details": str(e)}

def perform_local_search(query: str, lat: float = None, lng: float = None) -> dict:
    """Perform local search using SerpAPI GoogleSearch for location-based queries."""
    
    if lat is None or lng is None:
        lat, lng = USER_LAT, USER_LON
        logger.info(f"No lat/lng provided. Using random Bangkok location: ({lat}, {lng})")

    params = {
        "q": query,
        "location": "Bangkok, Thailand",
        "hl": "th",
        "gl": "th",
        "google_domain": "google.co.th",
        "api_key": SERPAPI_API_KEY,
        "ll": f"@{lat},{lng},14z",
        "tbm": "lcl"  
    }

    try:
        results = GoogleSearch(params).get_dict()
        logger.info(f"Full SerpAPI response keys: {list(results.keys())}")

        # Check for API errors first
        if "error" in results:
            logger.warning(f"SerpAPI returned error: {results['error']}")
            # Fallback to general search
            logger.info(f"Falling back to general search for: {query}")
            return perform_general_search(query, location="Bangkok, Thailand")

        places = []

        if "local_results" in results:
            local_results = results.get("local_results")
            logger.info(f"local_results type: {type(local_results)}")

            if isinstance(local_results, dict):
                places = local_results.get("places", [])
            elif isinstance(local_results, list):
                places = local_results

        if not places and "places" in results:
            places = results.get("places", [])

        if not places and "local_map_results" in results:
            places = results.get("local_map_results", [])

        # If still no places found, try general search as fallback
        if not places:
            logger.info(f"No local results found, falling back to general search for: {query}")
            return perform_general_search(query, location="Bangkok, Thailand")

        search_results = {
            "ai_overview": results.get("ai_overview", {}),
            "organic_results": results.get("organic_results", [])[:3],
            "answer_box": results.get("answer_box", {}),
            "knowledge_graph": results.get("knowledge_graph", {}),
            "places": places[:3] if places else [],
            "local_results": results.get("local_results", {})[:3],
            "full_response_keys": list(results.keys())
        }

        logger.info(f"Local search completed for query: {query}")
        logger.info(f"Places found: {len(places)}")
        if places:
            logger.info(f"First place example: {places[0] if places else 'None'}")
        else:
            logger.info(f"Available result keys: {list(results.keys())}")

        return search_results

    except Exception as e:
        logger.error(f"Error during local search: {e}", exc_info=True)
        # Fallback to general search
        logger.info(f"Exception occurred, falling back to general search for: {query}")
        return perform_general_search(query, location="Bangkok, Thailand")

def perform_general_search(query: str, location: str = None) -> dict:
    """Perform general web search using SerpAPI GoogleSearch for knowledge queries."""
    
    params = {
        "q": query,
        "hl": "en", 
        "gl": "th",  
        "api_key": SERPAPI_API_KEY

    }
    
    if location:
        params["location"] = location

    try:
        results = GoogleSearch(params).get_dict()
        logger.info(f"General search completed for query: {query}")
        
        search_results = {
            "ai_overview": results.get("ai_overview", {}),
            "organic_results": results.get("organic_results", [])[:5],  # More results for general queries
            "answer_box": results.get("answer_box", {}),
            "knowledge_graph": results.get("knowledge_graph", {}),
            "full_response_keys": list(results.keys())
        }
        
        logger.info(f"General search results keys: {list(search_results.keys())}")
        
        return search_results

    except Exception as e:
        logger.error(f"Error during general search: {e}", exc_info=True)
        return {"error": f"General search failed: {str(e)}"}

def create_gemini_prompt_with_search(statement="", search_results=None, conversation_context="", langChoice="en", routing=None, user_lat=None, user_lon=None):
    """Create Gemini prompt that includes search results, weather data, lottery data, and conversation context for web queries.

    Args:
        statement: User's query
        search_results: Results from search APIs
        conversation_context: Previous conversation history
        langChoice: Language choice (en/th/jp)
        routing: Routing decision dict from determine_query_requirements
        user_lat: User latitude (if location-based query)
        user_lon: User longitude (if location-based query)
    """
    local_intent = routing.get("needs_local_search", False) if routing else False
    weather_intent = routing.get("needs_weather", False) if routing else False
    lottery_intent = routing.get("needs_lottery", False) if routing else False

    location_context = f"""
    **IMPORTANT LOCATION CONTEXT:**
    - The user is currently located in Bangkok, Thailand
    - All search results above are based on Bangkok location
    - You should assume the user is asking about places in Bangkok unless they specify otherwise
    - Even if the search results don't explicitly mention Bangkok, treat them as Bangkok-based results
    - Do NOT ask for user's location or coordinates - assume Bangkok as the default location
    """ if local_intent else ""

    # Build jokes context — ONLY when the user actually asked for a joke
    jokes_context = ""
    needs_jokes = routing.get("needs_jokes", False) if routing else False
    if needs_jokes and 'csv' in JOKES_DATA and JOKES_DATA['csv']:
        # Select jokes based on language
        if langChoice == "th" and 'thai' in JOKES_DATA and JOKES_DATA['thai']:
            jokes_to_use = JOKES_DATA['thai']
            jokes_context += "\n**JOKES TO SHARE (Thai):**\n"
        elif langChoice == "en" and 'english' in JOKES_DATA and JOKES_DATA['english']:
            jokes_to_use = JOKES_DATA['english']
            jokes_context += "\n**JOKES TO SHARE (English):**\n"
        else:
            # Fallback to all jokes if language-specific not available
            jokes_to_use = JOKES_DATA['csv']
            jokes_context += "\n**JOKES TO SHARE:**\n"

        for i, joke in enumerate(jokes_to_use[:15], start=1):
            jokes_context += f"{i}. {joke}\n"

    # Dealership context removed — this portal IS the service center
    dealership_context = ""

    # Build car specifications context
    specifications_context = ""
    if CAR_SPECIFICATIONS:
        specifications_context = "\n**SERVICE CENTER INFORMATION:**\n"
        for key, spec_data in CAR_SPECIFICATIONS.items():
            feature = spec_data['feature']
            specification = spec_data['specification']
            specifications_context += f"- {feature}: {specification}\n"

    if search_results:
        search_context = f"""
        
**CRITICAL LANGUAGE INSTRUCTION - MUST FOLLOW:**
- Your response MUST be in {'Thai' if langChoice == 'th' else 'English'} language
- The `reply` field in the JSON output MUST be in {'Thai' if langChoice == 'th' else 'English'}
- This is MANDATORY and takes precedence over all other instructions
        
{conversation_context}
        
**SEARCH RESULTS FOR: "{statement}"**
"""

        # Handle weather-specific results
        if weather_intent and ('weather' in search_results or 'list' in search_results or 'hourly' in search_results or 'daily' in search_results or 'air_quality' in search_results):
            location_data = search_results.get('location', {})

            # Current weather
            if 'weather' in search_results:
                weather_data = search_results.get('weather', {})
                search_context += f"""

**CURRENT WEATHER INFORMATION:**
Location: {location_data.get('name', 'Bangkok')}, {location_data.get('country', 'Thailand')}
Temperature: {weather_data.get('temperature', 'N/A')}°C
Feels Like: {weather_data.get('feels_like', 'N/A')}°C
Description: {weather_data.get('description', 'N/A')}
Humidity: {weather_data.get('humidity', 'N/A')}%
Wind Speed: {weather_data.get('wind_speed', 'N/A')} m/s
Pressure: {weather_data.get('pressure', 'N/A')} hPa
Clouds: {weather_data.get('clouds', 'N/A')}%
"""

            # Daily/Hourly forecast (list format)
            elif 'list' in search_results:
                forecast_list = search_results.get('list', [])
                cnt = search_results.get('cnt', len(forecast_list))
                city_info = location_data.get('city', {})
                city_name = city_info.get('name', 'Bangkok') if isinstance(city_info, dict) else 'Bangkok'

                search_context += f"""

**WEATHER FORECAST INFORMATION:**
Location: {city_name}
Number of forecast periods: {cnt}
Forecast data: {json.dumps(forecast_list[:5], ensure_ascii=False, indent=2)}
(Showing first 5 periods. Use this data to answer the user's weather forecast question.)
"""

            # Air quality data (current, forecast, or historical)
            elif 'air_quality' in search_results or ('list' in search_results and ('is_forecast' in search_results or 'is_historical' in search_results)):
                # Current air quality (single reading)
                if 'air_quality' in search_results:
                    air_data = search_results.get('air_quality', {})
                    aqi = air_data.get('main', {}).get('aqi', 'N/A')
                    components = air_data.get('components', {})
                    search_context += f"""

**CURRENT AIR QUALITY INFORMATION:**
Location: Lat {location_data.get('lat')}, Lon {location_data.get('lon')}
Air Quality Index (AQI): {aqi} (1=Good, 2=Fair, 3=Moderate, 4=Poor, 5=Very Poor)
Components:
- CO (Carbon monoxide): {components.get('co', 'N/A')} μg/m³
- NO (Nitrogen monoxide): {components.get('no', 'N/A')} μg/m³
- NO2 (Nitrogen dioxide): {components.get('no2', 'N/A')} μg/m³
- O3 (Ozone): {components.get('o3', 'N/A')} μg/m³
- SO2 (Sulphur dioxide): {components.get('so2', 'N/A')} μg/m³
- PM2.5 (Fine particles): {components.get('pm2_5', 'N/A')} μg/m³
- PM10 (Coarse particles): {components.get('pm10', 'N/A')} μg/m³
- NH3 (Ammonia): {components.get('nh3', 'N/A')} μg/m³
"""
                # Air quality forecast (list of future readings)
                elif 'is_forecast' in search_results and 'list' in search_results:
                    forecast_list = search_results.get('list', [])
                    search_context += f"""

**AIR QUALITY FORECAST:**
Location: Lat {location_data.get('lat')}, Lon {location_data.get('lon')}
Number of forecast periods: {len(forecast_list)}

"""
                    # Show first 3 forecast periods with detailed breakdown
                    for i, period in enumerate(forecast_list[:3]):
                        from datetime import datetime
                        dt = period.get('dt', 0)
                        timestamp = datetime.fromtimestamp(dt).strftime('%Y-%m-%d %H:%M:%S') if dt else 'N/A'
                        aqi = period.get('main', {}).get('aqi', 'N/A')
                        components = period.get('components', {})
                        search_context += f"""Period {i+1} ({timestamp}):
- AQI: {aqi} (1=Good, 2=Fair, 3=Moderate, 4=Poor, 5=Very Poor)
- PM2.5: {components.get('pm2_5', 'N/A')} μg/m³
- PM10: {components.get('pm10', 'N/A')} μg/m³
- O3: {components.get('o3', 'N/A')} μg/m³
- NO2: {components.get('no2', 'N/A')} μg/m³

"""
                # Historical air quality (list of past readings)
                elif 'is_historical' in search_results and 'list' in search_results:
                    historical_list = search_results.get('list', [])
                    search_context += f"""

**HISTORICAL AIR QUALITY DATA:**
Location: Lat {location_data.get('lat')}, Lon {location_data.get('lon')}
Number of historical periods: {len(historical_list)}

"""
                    # Show first 3 historical periods with detailed breakdown
                    for i, period in enumerate(historical_list[:3]):
                        from datetime import datetime
                        dt = period.get('dt', 0)
                        timestamp = datetime.fromtimestamp(dt).strftime('%Y-%m-%d %H:%M:%S') if dt else 'N/A'
                        aqi = period.get('main', {}).get('aqi', 'N/A')
                        components = period.get('components', {})
                        search_context += f"""Period {i+1} ({timestamp}):
- AQI: {aqi} (1=Good, 2=Fair, 3=Moderate, 4=Poor, 5=Very Poor)
- PM2.5: {components.get('pm2_5', 'N/A')} μg/m³
- PM10: {components.get('pm10', 'N/A')} μg/m³
- O3: {components.get('o3', 'N/A')} μg/m³
- NO2: {components.get('no2', 'N/A')} μg/m³

"""

            search_context += f"""

**WEATHER RESPONSE FORMAT:**
For weather queries, you MUST return ONLY the following JSON format (no other text):
{{
    "command": "11111111",
    "reply": "YOUR_WEATHER_RESPONSE_IN_{'THAI' if langChoice == 'th' else 'ENGLISH'}",
    "openEndedValue": null
}}

**IMPORTANT:** Use the weather data provided above to answer the user's question. Do NOT ask for location - the data is already provided for the user's location.
"""
        # Handle error cases for weather
        elif weather_intent and 'error' in search_results:
            error_msg = search_results.get('error', 'Unknown error')
            search_context += f"""
**WEATHER ERROR:**
Error retrieving weather data: {error_msg}

Please provide a friendly response indicating that weather information is temporarily unavailable.
"""
        # Handle lottery-specific results
        elif lottery_intent and 'lottery_status' in search_results:
            lottery_status = search_results.get('lottery_status')
            date_info = search_results.get('date_info', {})

            if lottery_status == 'not_drawn':
                search_context += f"""

**LOTTERY INFORMATION:**
Status: Results not yet drawn
Date: {date_info.get('date', 'Unknown date')}
Date ID: {date_info.get('id', 'Unknown')}

**LOTTERY RESPONSE FORMAT:**
For lottery queries when results are not yet drawn, return the following JSON format:
{{
    "command": "11111110",
    "reply": "[Thai: ผลหวยยังไม่ออก สำหรับวันที่ {date_info.get('date', 'ไม่ทราบวันที่')} | English: Lottery results have not been drawn yet for {date_info.get('date', 'unknown date')}]",
    "openEndedValue": null
}}

**EXAMPLE RESPONSE:**
Thai: "ผลหวยยังไม่ออก สำหรับวันที่ {date_info.get('date', 'ไม่ทราบวันที่')} กรุณาตรวจสอบอีกครั้งหลังจากการออกรางวัล"
English: "Lottery results have not been drawn yet for {date_info.get('date', 'unknown date')}. Please check again after the drawing."

**NOTE:** The system uses the latest available lottery date (not in the future) to provide current results.
"""
            elif lottery_status == 'available':
                results = search_results.get('results', {})
                # Extract the source link from the API response
                source_link = ""
                if results and 'response' in results and 'endpoint' in results['response']:
                    source_link = results['response']['endpoint']

                search_context += f"""

**LOTTERY RESULTS:**
Date: {date_info.get('date', 'Unknown date')}
Date ID: {date_info.get('id', 'Unknown')}
Source Link: {source_link}
Results: {json.dumps(results, ensure_ascii=False, indent=2)}

**LOTTERY RESPONSE FORMAT:**
For lottery queries with available results, return the following JSON format:
{{
    "command": "11111110",
    "reply": "[Concise response based on query type - see below]",
    "openEndedValue": null
}}

**RESPONSE RULES:**
1. **General lottery query** (e.g., "lottery results", "what's the lottery number"):
   - ONLY provide the 1st prize number
   - Thai: "ผลหวยประจำวันที่ {date_info.get('date', 'ไม่ทราบวันที่')} รางวัลที่ 1: [เลขรางวัลที่ 1]"
   - English: "Lottery results for {date_info.get('date', 'unknown date')}: 1st Prize: [1st prize number]"
   - Example: "Lottery results for 16 กันยายน 2568: 1st Prize: 123456"

2. **User mentions a specific number** (e.g., "I bought 06", "is 123456 correct", "did I win with 789"):
   - Check the number against ALL prize categories (1st prize, 2-digit, 3-digit front, 3-digit back, etc.)
   - If it matches, congratulate them and specify which prize they won
   - Thai examples:
     * "ยินดีด้วยค่ะ คุณถูกรางวัลเลขท้าย 2 ตัว 06"
     * "ยินดีด้วยค่ะ คุณถูกรางวัลที่ 1 เลข 123456"
   - English examples:
     * "Congratulations! You won the last 2 digits prize with 06."
     * "Congratulations! You won the 1st prize with 123456."
   - If no match: "Sorry, your number [number] did not win any prize this time."

**IMPORTANT:**
1. Extract actual prize numbers from the results data
2. Only provide the lottery numbers and prize information - do NOT include any website links or URLs
3. The system uses the latest available lottery date (not in the future) to provide current results
4. Be concise - don't list all prizes unless the user specifically asks for them
"""
            else:
                search_context += f"""
**LOTTERY ERROR:**
Unable to retrieve lottery information.

Please provide a friendly response indicating that lottery information is temporarily unavailable.
"""
        # Handle lottery error cases
        elif lottery_intent and 'error' in search_results:
            error_msg = search_results.get('error', 'Unknown error')
            search_context += f"""
**LOTTERY ERROR:**
Error retrieving lottery data: {error_msg}

Please provide a friendly response indicating that lottery information is temporarily unavailable.
"""
        else:
            search_context += f"""
AI Overview: {json.dumps(search_results.get('ai_overview', {}), ensure_ascii=False, indent=2)}

Organic Results: {json.dumps(search_results.get('organic_results', []), ensure_ascii=False, indent=2)}

Answer Box: {json.dumps(search_results.get('answer_box', {}), ensure_ascii=False, indent=2)}

Knowledge Graph: {json.dumps(search_results.get('knowledge_graph', {}), ensure_ascii=False, indent=2)}

Places: {json.dumps(search_results.get('places', []), ensure_ascii=False, indent=2)}
"""

        lang_name = 'Thai' if langChoice == 'th' else 'English'
        data_type = "lottery data" if lottery_intent else "weather data" if weather_intent else "search results"

        search_context += f"""

{location_context}

**CRITICAL LANGUAGE REQUIREMENT - IMMEDIATE COMPLIANCE:**
- RESPOND IN: {'Thai' if langChoice == 'th' else 'English'} LANGUAGE ONLY
- ALL TEXT IN `reply` FIELD MUST BE: {'Thai' if langChoice == 'th' else 'English'}
- NO EXCEPTIONS - SWITCH LANGUAGE IMMEDIATELY

**INSTRUCTIONS:**
Based on the {data_type} above and the conversation context provided, provide a helpful response in {lang_name}.
- Synthesize the information from the {data_type}
- Present it in a clear, conversational manner
- Keep the response concise but informative
- For lottery queries: provide lottery results if available, or inform that results haven't been drawn yet
- For weather queries: provide current conditions with temperature, description, and relevant details
- For general knowledge: use AI Overview, Answer Box, and Organic Results
- For local queries: list specific Bangkok places with title, type, and address
- NEVER say you can't find something near Bangkok unless it's a local query and places are truly empty
- Use the {data_type} to answer about {"lottery results" if lottery_intent else "weather conditions" if weather_intent else "local queries in Bangkok"}
- NEVER ask for user's location or coordinates or suggest using certain websites. Only provide concrete answers with the names
and distance to nearest places.
- **Use the 'title', 'type', and 'address' fields from the places data to provide specific information for LOCAL QUERIES**
- **Consider the conversation history for context and continuity**
- Always incorporate jokes appropriately if the user asks for jokes or humor

**RESPONSE FORMATS:**"""

        if lottery_intent:
            search_context += """
**FOR LOTTERY QUERIES:**
Return the following JSON format for lottery questions:
{
    "command": "11111110",
    "reply": "YOUR_LOTTERY_RESPONSE_HERE",
    "openEndedValue": null
}"""
        elif weather_intent:
            search_context += """
**FOR WEATHER QUERIES:**
Return the following JSON format for weather questions:
{
    "command": "11111111",
    "reply": "YOUR_WEATHER_RESPONSE_HERE",
    "openEndedValue": null
}"""
        elif local_intent:
            search_context += """
**FOR LOCAL QUERIES ONLY:**
1. Return the following JSON format when it is a question that asks for the nearest restaurant:
{
    "command": "11111111",
    "reply": "YOUR_RESTAURANT_RESPONSE_HERE",
    "openEndedValue": null
}

2. Return the following JSON format when it is a question that asks for the nearest gas station:
{
    "command": "11111111",
    "reply": "YOUR_GAS_STATION_RESPONSE_HERE",
    "openEndedValue": null
}

3. Return ONLY the following JSON format if it is a question about other places or other questions:
{
    "command": "11111111",
    "reply": "YOUR_RESPONSE_HERE",
    "openEndedValue": null
}"""
        else:
            search_context += """
**FOR GENERAL QUERIES:**
Return the following JSON format for general knowledge questions:
{
    "command": "11111111",
    "reply": "YOUR_RESPONSE_HERE",
    "openEndedValue": null
}"""

        search_context += f"""

User query: {statement}
"""
        return search_context.strip()

    # Only perform semantic manual search if the query requires it (use routing results)
    car_specs_context = ""
    manual_needed = routing.get("needs_car_manual", False) if routing else False

    if manual_needed:
        # Get optimized search phrases from routing (if available)
        search_phrases = routing.get("manual_search_phrases", []) if routing else []
        logger.info(f"Performing semantic manual search for: '{statement}' (routing: needs_car_manual={manual_needed}, search_phrases={search_phrases})")
        car_specs_context = get_car_specifications_context(statement, search_phrases=search_phrases)
    else:
        logger.info(f"Skipping manual search for: '{statement}' (routing: needs_car_manual={manual_needed})")

    lang_name = 'Thai' if langChoice == 'th' else 'English'
    prompt = f"""

**MANDATORY LANGUAGE SETTING - APPLY IMMEDIATELY:**
- ALL responses must be in {'Thai' if langChoice == 'th' else 'English'} language
- The `reply` field MUST be in {'Thai' if langChoice == 'th' else 'English'}
- Switch language NOW - no delays or buffers

{conversation_context}

{car_specs_context}

{jokes_context}

{dealership_context}

{specifications_context}

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
4. Ask for **preferred date**
5. Ask for **preferred time** (remind: 8 AM–5 PM, Mon–Sat)
6. Ask for **phone number** — say exactly: "Could I get your phone number please?"
7. Ask for **email address** — say exactly: "And your email address please?"
8. **Read back ALL details** and ask them to confirm
9. Once confirmed: say "Your appointment is confirmed! We'll see you on [date] at [time]. Goodbye and have a great day!" — end the conversation warmly

IMPORTANT: Collect ALL details in this exact order. Do NOT ask for phone or email before getting vehicle, service, date and time.

**CONVERSATION CONTINUITY:**
- Always consider the conversation history above when responding
- Maintain context across the conversation
- If the customer refers to "that", "it", or previous context, use the history to understand

**OUTPUT FORMAT:**
You MUST return ONLY a JSON object:
{{
  "command": "11111111",
  "reply": "YOUR_RESPONSE_HERE",
  "openEndedValue": null
}}

Use `"command": "11111110"` for informational/how-to responses.
Use `"command": null` only if the request is completely outside your scope (e.g., booking a flight, doing homework).

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

# --- Smart Query Routing with Gemini Flash ---
_NULL_ROUTING = {
    "needs_weather": False, "needs_local_search": False, "needs_lottery": False,
    "needs_car_manual": False, "needs_car_commands": False, "needs_jokes": False,
    "needs_dealership": False, "needs_web_search": False,
    "query_type": "appointment_service", "manual_search_phrases": [],
    "optimized_search_query": "", "weather_query_type": "",
    "weather_time_context": "", "weather_days_ahead": 0
}

# Keywords that signal external data is actually needed — everything else skips Gemini routing
import re as _re
_NEEDS_ROUTING_RE = _re.compile(
    r'\b(weather|forecast|rain|temperature|temp|hot|cold|humid|sunny|cloudy|storm|typhoon|flood|'
    r'air quality|aqi|pollution|pm2\.?5|'
    r'nearby|near me|around here|closest|restaurant|cafe|coffee|food|eat|hotel|hospital|clinic|gas station|petrol|'
    r'lottery|lotto|lucky number|หวย|เลขเด็ด|'
    r'joke|funny|tell me a joke|make me laugh|'
    r'news|latest|current events|who is|what happened|who won|'
    r'อากาศ|ฝน|อุณหภูมิ|ร้าน|ใกล้)\b',
    _re.IGNORECASE
)


async def determine_query_requirements(command_text: str) -> dict:
    """Use Gemini Flash (fastest) to intelligently determine what data sources are needed for the query.

    Returns:
        dict with keys:
            - needs_weather: bool (weather queries)
            - needs_local_search: bool (nearby places queries)
            - needs_lottery: bool (lottery/lucky numbers queries)
            - needs_car_manual: bool (how-to car questions)
            - needs_car_commands: bool (instructional commands like "turn on AC")
            - needs_jokes: bool (joke requests)
            - needs_dealership: bool (dealership queries)
            - needs_web_search: bool (general knowledge/current events)
            - query_type: str (description of query type)
            - weather_query_type: str (current/hourly_forecast/daily_forecast/air_pollution)
            - weather_time_context: str (now/today/tomorrow/specific date/range)
    """
    # Fast path: appointment/service/greeting messages never need external APIs.
    # Skip the Gemini routing call entirely — saves 0.5–2 sec per request.
    if not _NEEDS_ROUTING_RE.search(command_text):
        logger.info(f"Fast routing (no external data needed) for: '{command_text}'")
        return dict(_NULL_ROUTING)

    if not gemini_routing_model:
        logger.error("Gemini routing model not available")
        return {
            "needs_weather": False,
            "needs_local_search": False,
            "needs_lottery": False,
            "needs_car_manual": False,
            "needs_car_commands": False,
            "needs_jokes": False,
            "needs_dealership": False,
            "needs_web_search": False,
            "query_type": "error_no_model",
            "manual_search_phrases": [],
            "optimized_search_query": "",
            "weather_query_type": "",
            "weather_time_context": "",
            "weather_days_ahead": 0
        }

    routing_prompt = f"""You are a smart query router for a CAR SERVICE CENTER ASSISTANT (Sarah from ABC Car Service Center). Customers contact this portal to book appointments, ask about services, and get general car advice.

**IMPORTANT CONTEXT:**
- This is a SERVICE CENTER assistant — not an in-car assistant
- Most queries will be about booking appointments, service questions, or general car maintenance advice
- "How to" questions about car maintenance go to Car Manual
- Do NOT route to dealership — this portal IS the service center

Available data sources:
1. **Weather API** - For weather queries (current weather, hourly/daily forecasts, air pollution)
   - Current weather: temperature, conditions right now
   - Hourly forecast: next 48 hours (4 days)
   - Daily forecast: next 16 days
   - Air pollution: current, forecast, or historical air quality data
2. **Local Search API** - For nearby places (restaurants, gas stations, tourist spots, hotels)
3. **Lottery API** - For lottery results, lucky numbers, winning numbers (keywords: lottery, lotto, หวย, เลขเด็ด)
4. **Car Manual PDF** - For car maintenance "how to" questions (e.g., "how often oil change", "what is a service interval")
5. **Jokes CSV** - For joke requests
6. **Web Search** - For general knowledge, current events, news

User query: "{command_text}"

Analyze this query and respond with JSON only:
{{
    "needs_weather": true/false,
    "needs_local_search": true/false,
    "needs_lottery": true/false,
    "needs_car_manual": true/false,
    "needs_car_commands": true/false,
    "needs_jokes": true/false,
    "needs_dealership": true/false,
    "needs_web_search": true/false,
    "query_type": "brief description of query type",
    "manual_search_phrases": ["phrase1", "phrase2", "phrase3"],
    "optimized_search_query": "optimized search query for web/local search",
    "weather_query_type": "current|hourly_forecast|daily_forecast|air_pollution_current|air_pollution_forecast|air_pollution_historical",
    "weather_time_context": "now|today|tomorrow|next_week|specific_date|date_range",
    "weather_days_ahead": 0
}}

Rules:
- Only set ONE primary data source to true (the most relevant one)
- Weather queries (temperature, forecast) → needs_weather only
- Nearby places (restaurants, gas stations) → needs_local_search only
- Lottery/lucky numbers → needs_lottery only
- Car maintenance "how to" questions → needs_car_manual only
- Jokes → needs_jokes only
- Dealership/service center queries → needs_web_search=false, needs_dealership=false (handle in prompt)
- General knowledge/current events → needs_web_search only
- Appointment booking, service questions, general car advice → all false (handled directly by Sarah)
- **Default: most customer queries need no external data source**

**WEATHER QUERY TYPE DETECTION:**
If needs_weather is true, determine the specific weather query type:
- **"air_pollution_current"**: Current air quality NOW (keywords: air quality, pollution, AQI, smog, air pollution - WITHOUT time context)
- **"air_pollution_forecast"**: Air quality forecast for FUTURE (keywords: air quality tomorrow, pollution tomorrow, air pollution tomorrow, AQI tomorrow, pollution forecast, air quality next week)
- **"air_pollution_historical"**: Past air quality data (keywords: air quality yesterday, pollution last week, AQI last month)
- **"current"**: Current weather right now (keywords: now, current, currently, what's the weather - WITHOUT air pollution keywords)
- **"hourly_forecast"**: Hourly forecast for next 48 hours (keywords: hourly, next few hours, this afternoon, tonight - WITHOUT air pollution keywords)
- **"daily_forecast"**: Daily forecast up to 16 days (keywords: tomorrow, next week, this weekend, next 5 days - WITHOUT air pollution keywords)

**IMPORTANT:** If the query contains "air pollution", "air quality", "AQI", or "pollution" keywords, it MUST be classified as air_pollution_* type, NOT as weather forecast type!

**WEATHER TIME CONTEXT:**
- **"now"**: Current moment (what's the weather, how's the weather)
- **"today"**: Today's weather
- **"tomorrow"**: Tomorrow's weather (set weather_days_ahead=1)
- **"next_week"**: Next 7 days (set weather_days_ahead=7)
- **"specific_date"**: Specific date mentioned (extract days ahead)
- **"date_range"**: Range of dates (for historical air pollution)

**WEATHER DAYS AHEAD:**
- Extract number of days from now (0=today, 1=tomorrow, 7=next week, etc.)
- For "next 3 days" → weather_days_ahead=3
- For "this weekend" → weather_days_ahead=2 (assuming Friday query)
- Maximum 16 for daily forecast

**WEATHER QUERY EXAMPLES:**
- "air pollution" → air_pollution_current
- "air quality" → air_pollution_current
- "air pollution tomorrow" → air_pollution_forecast
- "air quality tomorrow" → air_pollution_forecast
- "pollution forecast" → air_pollution_forecast
- "AQI tomorrow" → air_pollution_forecast
- "will it rain tomorrow" → daily_forecast (NOT air pollution)
- "weather tomorrow" → daily_forecast (NOT air pollution)
- "temperature tomorrow" → daily_forecast (NOT air pollution)

**IMPORTANT - Manual Search Phrases:**
- If needs_car_manual is true, generate 2-4 optimized search phrases for semantic search
- Extract key concepts and rephrase into short, searchable terms
- Focus on the core action/feature being asked about
- Remove filler words like "how to", "can I", "is it possible", etc.
- Examples:
  * "how can I troubleshoot when my car isn't starting" → ["start car", "engine start", "troubleshoot starting", "car won't start"]
  * "how to turn on wifi" → ["wifi", "turn on wifi", "wifi setup"]
  * "where is the spare tire located" → ["spare tire", "tire location", "spare tire storage"]
  * "how do I connect my phone via bluetooth" → ["bluetooth", "phone connection", "bluetooth pairing"]
- If needs_car_manual is false, set manual_search_phrases to empty array []

**CRITICAL - Optimized Search Query:**
- If needs_local_search or needs_web_search is true, generate a concise, direct search query
- Transform vague/conversational queries into specific, searchable terms
- For local searches, include location context (Bangkok) and specific place type
- For web searches, extract the core information need
- Examples:
  * "I'm so hungry" → "restaurants near me Bangkok"
  * "I'm bored" → "entertainment activities Bangkok"
  * "where should we go to dinner tonight" → "dinner restaurants Bangkok"
  * "find me a toilet" → "public restrooms near me Bangkok"
  * "who won the World Cup in 2002" → "2002 World Cup winner"
  * "what's the price of gold today" → "gold price today Thailand"
  * "I want to go to Japan" → "Japan travel information"
- If not a search query, set optimized_search_query to empty string ""

Examples:
- "how to turn on wifi" → needs_car_manual=true, manual_search_phrases=["wifi", "turn on wifi", "wifi setup"], optimized_search_query="", weather_query_type="", weather_time_context="", weather_days_ahead=0
- "how to connect bluetooth" → needs_car_manual=true, manual_search_phrases=["bluetooth", "phone connection", "bluetooth pairing"], optimized_search_query="", weather_query_type="", weather_time_context="", weather_days_ahead=0
- "turn on AC" → needs_car_commands=true, manual_search_phrases=[], optimized_search_query="", weather_query_type="", weather_time_context="", weather_days_ahead=0
- "what's the weather" → needs_weather=true, manual_search_phrases=[], optimized_search_query="", weather_query_type="current", weather_time_context="now", weather_days_ahead=0
- "what's the weather tomorrow" → needs_weather=true, manual_search_phrases=[], optimized_search_query="", weather_query_type="daily_forecast", weather_time_context="tomorrow", weather_days_ahead=1
- "hourly forecast for today" → needs_weather=true, manual_search_phrases=[], optimized_search_query="", weather_query_type="hourly_forecast", weather_time_context="today", weather_days_ahead=0
- "weather for next week" → needs_weather=true, manual_search_phrases=[], optimized_search_query="", weather_query_type="daily_forecast", weather_time_context="next_week", weather_days_ahead=7
- "is the air quality good" → needs_weather=true, manual_search_phrases=[], optimized_search_query="", weather_query_type="air_pollution_current", weather_time_context="now", weather_days_ahead=0
- "air pollution forecast" → needs_weather=true, manual_search_phrases=[], optimized_search_query="", weather_query_type="air_pollution_forecast", weather_time_context="today", weather_days_ahead=0
- "find restaurants nearby" → needs_local_search=true, manual_search_phrases=[], optimized_search_query="restaurants near me Bangkok", weather_query_type="", weather_time_context="", weather_days_ahead=0
- "I'm hungry" → needs_local_search=true, manual_search_phrases=[], optimized_search_query="restaurants near me Bangkok", weather_query_type="", weather_time_context="", weather_days_ahead=0
- "lottery results" → needs_lottery=true, manual_search_phrases=[], optimized_search_query="", weather_query_type="", weather_time_context="", weather_days_ahead=0
- "tell me a joke" → needs_jokes=true, manual_search_phrases=[], optimized_search_query="", weather_query_type="", weather_time_context="", weather_days_ahead=0
- "who won the World Cup" → needs_web_search=true, manual_search_phrases=[], optimized_search_query="World Cup winner", weather_query_type="", weather_time_context="", weather_days_ahead=0

Respond with JSON only, no explanation."""

    try:
        # Use the faster routing model for quick decisions
        response = await gemini_routing_model.generate_content_async(
            routing_prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.0,
                max_output_tokens=250  # Increased to accommodate weather routing fields
            )
        )

        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            raw_text = response.candidates[0].content.parts[0].text.strip()

            # Log raw response for debugging
            if not raw_text:
                logger.error(f"Empty response from Gemini routing model for query: '{command_text}'")
                logger.error(f"Response object: {response}")
                # Return default routing on empty response
                return {
                    "needs_weather": False,
                    "needs_local_search": False,
                    "needs_lottery": False,
                    "needs_car_manual": False,
                    "needs_car_commands": False,
                    "needs_jokes": False,
                    "needs_dealership": False,
                    "needs_web_search": True,  # Default to web search as fallback
                    "query_type": "error_empty_response",
                    "manual_search_phrases": [],
                    "optimized_search_query": "",
                    "weather_query_type": "",
                    "weather_time_context": "",
                    "weather_days_ahead": 0
                }

            # Extract JSON
            try:
                json_match = re.search(r"```json\s*({.*?})\s*```|({.*?})", raw_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1) or json_match.group(2)
                    result = json.loads(json_str.strip())
                else:
                    result = json.loads(raw_text)

                logger.info(f"Query routing result: {result}")
                return result
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse routing JSON. Raw response: {raw_text[:500]}")
                logger.error(f"JSON decode error: {e}")
                # Return default routing on parse error
                return {
                    "needs_weather": False,
                    "needs_local_search": False,
                    "needs_lottery": False,
                    "needs_car_manual": False,
                    "needs_car_commands": False,
                    "needs_jokes": False,
                    "needs_dealership": False,
                    "needs_web_search": True,  # Default to web search as fallback
                    "query_type": "error_json_parse",
                    "manual_search_phrases": [],
                    "optimized_search_query": "",
                    "weather_query_type": "",
                    "weather_time_context": "",
                    "weather_days_ahead": 0
                }
        else:
            logger.warning("No valid response from Gemini routing model")
            return {
                "needs_weather": False,
                "needs_local_search": False,
                "needs_lottery": False,
                "needs_car_manual": False,
                "needs_car_commands": False,
                "needs_jokes": False,
                "needs_dealership": False,
                "needs_web_search": False,
                "query_type": "error_no_response",
                "manual_search_phrases": [],
                "optimized_search_query": "",
                "weather_query_type": "",
                "weather_time_context": "",
                "weather_days_ahead": 0
            }

    except Exception as e:
        logger.error(f"Error in smart query routing: {e}")
        return {
            "needs_weather": False,
            "needs_local_search": False,
            "needs_lottery": False,
            "needs_car_manual": False,
            "needs_car_commands": False,
            "needs_jokes": False,
            "needs_dealership": False,
            "needs_web_search": False,
            "query_type": "error_exception",
            "manual_search_phrases": [],
            "optimized_search_query": "",
            "weather_query_type": "",
            "weather_time_context": "",
            "weather_days_ahead": 0
        }

# --- Core Command Processing Logic (Modified for SerpAPI integration) ---
async def get_ai_command_response(command_text: str, lat: float = None, lng: float = None, session_id: str = None, langChoice: str = None) -> dict:
    """Process command with Gemini, including web search results and conversation history if needed."""
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
    logger.info(f"Processing command with Gemini: '{command_text}' for session: {session.session_id}")

    conversation_context = session.get_context_for_gemini(command_text)

    # Use smart routing to determine what data sources are needed
    routing = await determine_query_requirements(command_text)
    logger.info(f"Smart routing for '{command_text}': {routing['query_type']} - {routing}")

    # Only fetch data that's actually needed - call specific search functions directly based on routing
    search_results = None
    needs_location = False

    if routing.get("needs_weather"):
        # Weather query - use lat/lng and route to correct API based on query type
        if lat is None or lng is None:
            lat, lng = USER_LAT, USER_LON
            logger.info(f"Weather query. Using random Bangkok location: ({lat}, {lng})")

        weather_query_type = routing.get("weather_query_type", "current")
        weather_days_ahead = routing.get("weather_days_ahead", 0)
        lang_code = "th" if langChoice == "th" else "en"

        # Route to appropriate weather API based on query type
        if weather_query_type == "hourly_forecast":
            search_results = perform_hourly_forecast(lat=lat, lon=lng, lang=lang_code)
            logger.info(f"Performed hourly forecast search for: '{command_text}'")
        elif weather_query_type == "daily_forecast":
            days = max(1, weather_days_ahead) if weather_days_ahead > 0 else 7
            search_results = perform_daily_forecast(lat=lat, lon=lng, days=days, lang=lang_code)
            logger.info(f"Performed daily forecast search ({days} days) for: '{command_text}'")
        elif weather_query_type == "air_pollution_current":
            search_results = perform_air_pollution_current(lat=lat, lon=lng)
            logger.info(f"Performed current air pollution search for: '{command_text}'")
        elif weather_query_type == "air_pollution_forecast":
            search_results = perform_air_pollution_forecast(lat=lat, lon=lng)
            logger.info(f"Performed air pollution forecast search for: '{command_text}'")
        elif weather_query_type == "air_pollution_historical":
            # For historical data, we need start and end timestamps
            # Default to last 24 hours if not specified
            import time
            end_time = int(time.time())
            start_time = end_time - (24 * 3600)  # 24 hours ago
            search_results = perform_air_pollution_historical(lat=lat, lon=lng, start=start_time, end=end_time)
            logger.info(f"Performed historical air pollution search for: '{command_text}'")
        else:
            # Default to current weather
            search_results = perform_weather_search(lat=lat, lon=lng, lang=lang_code)
            logger.info(f"Performed current weather search for: '{command_text}'")

        needs_location = True

    elif routing.get("needs_local_search"):
        # Local search query - use lat/lng
        if lat is None or lng is None:
            lat, lng = USER_LAT, USER_LON
            logger.info(f"Local search query. Using random Bangkok location: ({lat}, {lng})")
        # Use optimized search query if available for faster, more accurate results
        search_query = routing.get("optimized_search_query", "") or command_text
        if search_query != command_text:
            logger.info(f"Using optimized search query: '{search_query}' (original: '{command_text}')")
        search_results = perform_local_search(search_query, lat, lng)
        needs_location = True
        logger.info(f"Performed local search for: '{search_query}'")

    elif routing.get("needs_lottery"):
        # Lottery query - no location needed
        search_results = perform_lottery_search(command_text)
        logger.info(f"Performed lottery search for: '{command_text}'")

    elif routing.get("needs_dealership"):
        # Dealership query - needs location for distance calculation
        if lat is None or lng is None:
            lat, lng = USER_LAT, USER_LON
            logger.info(f"Dealership query. Using random Bangkok location: ({lat}, {lng})")
        needs_location = True
        logger.info(f"Dealership query detected for: '{command_text}' - will calculate distances from ({lat}, {lng})")

    elif routing.get("needs_web_search"):
        # General web search - no location needed
        # Use optimized search query if available for faster, more accurate results
        search_query = routing.get("optimized_search_query", "") or command_text
        if search_query != command_text:
            logger.info(f"Using optimized search query: '{search_query}' (original: '{command_text}')")
        search_results = perform_general_search(search_query)
        logger.info(f"Performed general web search for: '{search_query}'")

    else:
        logger.info(f"No external search needed for '{command_text}' - using {routing['query_type']}")

    # Compose prompt for Gemini (only pass lat/lng if location was needed)
    if needs_location:
        prompt = create_gemini_prompt_with_search(command_text, search_results, conversation_context, langChoice, routing, user_lat=lat, user_lon=lng)
    else:
        prompt = create_gemini_prompt_with_search(command_text, search_results, conversation_context, langChoice, routing, user_lat=None, user_lon=None)

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
                    json_match = re.search(r"```json\s*({.*?})\s*```|({.*?})", raw_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1) or json_match.group(2)
                        logger.info(f"Extracted JSON from markdown: '{json_str[:200]}'")
                        parsed_json = json.loads(json_str.strip())
                    else:
                        logger.info(f"Attempting to parse raw text as JSON")
                        parsed_json = json.loads(raw_text)

                    if not all(k in parsed_json for k in ["command", "reply", "openEndedValue"]):
                        logger.warning(f"AI response missing required keys: {parsed_json}")
                        raise ValueError("Missing required keys in AI JSON response")

                    logger.info(f"Successfully parsed Gemini response: command={parsed_json.get('command')}, reply_length={len(parsed_json.get('reply', ''))}")

                    # Save assistant's reply to session history
                    session.add_message("assistant", parsed_json.get("reply", ""))

                    return parsed_json
                except json.JSONDecodeError as json_err:
                    logger.error(f"Failed to parse JSON from Gemini: {json_err}. Raw text: '{raw_text}'")
                    return {
                        "command": None,
                        "reply": "Error: AI response was not valid JSON.",
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
    await initialize_semantic_search()
    await initialize_groq_client()

    car_manual_path = "car_manual.pdf"  # 126-page manual
    car_commands_path = "car_commands.csv"  # Car commands CSV
    car_specifications_path = "car_specifications.csv"  # Car specifications CSV
    jokes_path = "jokes.csv"
    dealerships_path = "dealerships.csv"

    # Load car commands from CSV
    if Path(car_commands_path).exists():
        await load_car_commands_from_csv(car_commands_path)
    else:
        logger.warning(f"Car commands CSV file not found: {car_commands_path}")

    # Load car specifications from CSV
    if Path(car_specifications_path).exists():
        await load_car_specifications_from_csv(car_specifications_path)
    else:
        logger.warning(f"Car specifications CSV file not found: {car_specifications_path}")

    if Path(jokes_path).exists():
        await load_jokes_from_csv(jokes_path)
    else:
        logger.warning(f"CSV file not found: {jokes_path}")

    if Path(dealerships_path).exists():
        await load_dealerships_from_csv(dealerships_path)
    else:
        logger.warning(f"CSV file not found: {dealerships_path}")

    # Load car manual with semantic search (preferred) or fallback to basic PDF
    if Path(car_manual_path).exists():
        success = await load_car_manual_with_embeddings(car_manual_path)
        if not success:
            logger.warning("Failed to load car manual with embeddings, trying basic PDF loading")
            await load_car_data_from_pdf(car_manual_path)
    else:
        logger.warning("No car manual found - place car_manual.pdf in the backend directory")

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
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.chat_history = []
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
    
    def add_message(self, role: str, content: str):
        self.chat_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        self.last_activity = datetime.now()
    
    def get_context_for_gemini(self, current_statement: str) -> str:
        """Create context string from chat history for Gemini"""
        if not self.chat_history:
            return ""
        
        context = "\n**CONVERSATION HISTORY:**\n"
        for msg in self.chat_history[-6:]:  
            role_display = "User" if msg["role"] == "user" else "Assistant"
            context += f"{role_display}: {msg['content']}\n"
        
        context += f"\n**CURRENT USER INPUT:** {current_statement}\n"
        context += "\n**IMPORTANT:** Consider the conversation history above when responding. Maintain context and continuity.\n\n"
        return context
    
    def is_expired(self) -> bool:
        return datetime.now() - self.last_activity > SESSION_TIMEOUT
    
class CarDataRequest(BaseModel):
    manual_path: Optional[str] = None
    force_rebuild: Optional[bool] = False

@app.post("/reload-car-data/")
async def reload_car_data(request: CarDataRequest):
    """Reload car manual data"""
    results = {}

    if request.manual_path and Path(request.manual_path).exists():
        success = await load_car_manual_with_embeddings(request.manual_path, request.force_rebuild)
        if success:
            results['manual'] = f"loaded with embeddings ({len(MANUAL_PAGES)} pages)"
        else:
            # Fallback to basic PDF loading
            success = await load_car_data_from_pdf(request.manual_path)
            results['manual'] = "loaded as basic PDF" if success else "failed"

    return {
        "message": "Car manual reload completed",
        "results": results,
        "semantic_search_available": SEMANTIC_SEARCH_AVAILABLE,
        "pages_loaded": len(MANUAL_PAGES) if MANUAL_PAGES else 0
    }

@app.get("/car-data-status/")
async def get_car_data_status():
    """Get current car data loading status"""
    status = {
        "semantic_search_available": SEMANTIC_SEARCH_AVAILABLE,
        "manual_pages_loaded": len(MANUAL_PAGES) if MANUAL_PAGES else 0,
        "dealerships_loaded": len(DEALERSHIPS_DATA.get('nearest', [])),
        "jokes_loaded": len(JOKES_DATA.get('csv', [])),
        "jokes_english": len(JOKES_DATA.get('english', [])),
        "jokes_thai": len(JOKES_DATA.get('thai', [])),
        "specifications_loaded": len(CAR_SPECIFICATIONS)
    }

    if 'csv' in CAR_DATA:
        status['csv'] = f"{len(CAR_DATA['csv'])} records loaded"
    if 'docx' in CAR_DATA:
        status['docx'] = f"{len(CAR_DATA['docx']['paragraphs'])} paragraphs, {len(CAR_DATA['docx']['tables'])} tables loaded"
    
    return {
        "loaded_data": status,
        "available_keys": list(CAR_DATA.keys())
    }

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

# --- API Endpoint (Modified) ---
class CommandRequest(BaseModel):
    command_text: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    session_id: Optional[str] = None
    langChoice: str

@app.post("/process-command/", response_class=JSONResponse)
async def process_command_endpoint(request_data: CommandRequest):
    """Process command using Gemini with integrated SerpAPI search and conversation history when needed."""
    command_text = request_data.command_text
    lat = request_data.lat
    lng = request_data.lng
    session_id = request_data.session_id
    langChoice = request_data.langChoice

    if lat is None or lng is None:
        lat, lng = USER_LAT, USER_LON
        logger.info(f"No lat/lng provided. Using random Bangkok location: ({lat}, {lng})")

    if not command_text:
        raise HTTPException(status_code=400, detail="command_text cannot be empty")

    logger.info(f"Received API request: '{command_text}' with lat/lng: {lat}, {lng}, session: {session_id}, langChoice: {langChoice}")

    ai_response_dict = await get_ai_command_response(command_text, lat=lat, lng=lng, session_id=session_id, langChoice=langChoice)

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
    lat: Optional[float] = Form(None),
    lng: Optional[float] = Form(None),
    session_id: Optional[str] = Form(None),
    langChoice: str = Form("en"),
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

            # Voice Activity Detection (if enabled and library available)
            # auto_stop_detected = False
            # vad_info = {
            #     "enabled": enable_auto_stop,
            #     "available": VOICE_RECOGNITION_AVAILABLE,
            #     "silence_threshold": silence_threshold
            # }

            # if enable_auto_stop and VOICE_RECOGNITION_AVAILABLE:
            #     try:
            #         # Initialize voice recognition library
            #         vr_lib = VoiceRecognitionLibrary()
            #         if vr_lib.initialize():
            #             # Convert audio data for analysis
            #             logger.info(f"VAD: Processing audio data, size: {len(audio_data)} bytes")

            #             if NUMPY_AVAILABLE:
            #                 try:
            #                     # Ensure buffer size is even for 16-bit samples
            #                     if len(audio_data) % 2 != 0:
            #                         audio_data = audio_data[:-1]
            #                         logger.info(f"VAD: Adjusted buffer size to {len(audio_data)} bytes")

            #                     audio_array = np.frombuffer(audio_data, dtype=np.int16)
            #                     logger.info(f"VAD: Numpy array created, shape: {audio_array.shape}")
            #                 except Exception as e:
            #                     logger.error(f"VAD: Numpy processing failed: {e}, using raw bytes")
            #                     audio_array = audio_data
            #             else:
            #                 # Use raw bytes if numpy not available
            #                 audio_array = audio_data
            #                 logger.info(f"VAD: Using raw bytes, size: {len(audio_array)}")

            #             # Check if this audio chunk indicates silence/end of speech
            #             try:
            #                 is_silence = vr_lib.detect_silence(audio_array, silence_threshold)
            #                 volume = vr_lib.calculate_volume(audio_array)
            #                 logger.info(f"VAD: Analysis complete - volume: {volume}, silence: {is_silence}")
            #             except Exception as e:
            #                 logger.error(f"VAD: Analysis failed: {e}")
            #                 raise e

            #             logger.info(f"VAD Analysis - Volume: {volume}, Is Silence: {is_silence}, Threshold: {silence_threshold}")

            #             # Simple auto-stop logic: if volume is very low, suggest stopping
            #             if volume < silence_threshold:
            #                 auto_stop_detected = True
            #                 logger.info(f"Auto-stop detected - low volume: {volume}")

            #             # Add detailed VAD info
            #             vad_info.update({
            #                 "volume": volume,
            #                 "is_silence": is_silence,
            #                 "auto_stop_detected": auto_stop_detected
            #             })

            #     except Exception as vad_error:
            #         logger.warning(f"VAD processing failed: {vad_error}")
            #         vad_info["error"] = str(vad_error)
                    # Continue with normal processing even if VAD fails

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
    # Note: lat/lng will be set to default only if actually needed by the query
    if lat is None or lng is None:
        lat, lng = USER_LAT, USER_LON

    if not command_text.strip():
        raise HTTPException(status_code=400, detail="command_text cannot be empty")

    logger.info(f"Processing command: '{command_text}', session: {session_id}, langChoice: {langChoice}")

    ai_response_dict = await get_ai_command_response(command_text, lat=lat, lng=lng, session_id=session_id, langChoice=langChoice)

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

# Voice Activity Detection Endpoints
class VoiceDetectionRequest(BaseModel):
    session_id: str
    silence_threshold: Optional[int] = 500
    min_speech_duration_ms: Optional[int] = 500
    silence_duration_ms: Optional[int] = 1500

@app.post("/voice/start-detection")
async def start_voice_detection(request: VoiceDetectionRequest):
    """Start voice activity detection with auto-stop on silence"""
    if not VOICE_RECOGNITION_AVAILABLE:
        raise HTTPException(status_code=503, detail="Voice recognition library not available")

    try:
        # Initialize voice recognition library if not already done
        vr_lib = VoiceRecognitionLibrary()
        if not vr_lib.initialize():
            raise HTTPException(status_code=500, detail="Failed to initialize voice recognition")

        # Store the library instance in session (in a real app, use proper session management)
        session_key = f"vr_session_{request.session_id}"

        # Setup callbacks for silence detection
        def on_silence_detected(result):
            logger.info(f"Silence detected for session {request.session_id}")
            # Here you would trigger the auto-stop mechanism

        def on_speech_detected(result):
            logger.info(f"Speech detected for session {request.session_id}, volume: {result.nVolume}")

        vr_lib.on_silence_detected = on_silence_detected
        vr_lib.on_speech_detected = on_speech_detected

        # Start recognition
        if not vr_lib.start_recognition():
            raise HTTPException(status_code=500, detail="Failed to start voice recognition")

        # Store in global dict (in production, use proper session storage)
        if not hasattr(app.state, 'voice_sessions'):
            app.state.voice_sessions = {}
        app.state.voice_sessions[session_key] = vr_lib

        return {
            "message": "Voice detection started successfully",
            "session_id": request.session_id,
            "silence_threshold": request.silence_threshold,
            "min_speech_duration_ms": request.min_speech_duration_ms,
            "silence_duration_ms": request.silence_duration_ms
        }

    except Exception as e:
        logger.error(f"Error starting voice detection: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start voice detection: {str(e)}")

@app.post("/voice/add-samples")
async def add_voice_samples(
    session_id: str = Form(...),
    audio_file: UploadFile = File(...)
):
    """Add audio samples to voice activity detection"""
    if not VOICE_RECOGNITION_AVAILABLE:
        raise HTTPException(status_code=503, detail="Voice recognition library not available")

    session_key = f"vr_session_{session_id}"

    if not hasattr(app.state, 'voice_sessions') or session_key not in app.state.voice_sessions:
        raise HTTPException(status_code=404, detail="Voice detection session not found")

    try:
        vr_lib = app.state.voice_sessions[session_key]

        # Read audio file
        audio_data = await audio_file.read()

        # Convert audio to numpy array (assuming 16-bit PCM)
        audio_array = np.frombuffer(audio_data, dtype=np.int16)

        # Add samples to voice recognition
        result = vr_lib.add_samples(audio_array)

        # Check result status
        if result == STATUS_SUCCESS:
            # Get the recognition result
            recog_result = vr_lib.get_result()
            return {
                "status": "completed",
                "message": "Voice detection completed",
                "session_id": session_id,
                "result": {
                    "volume": recog_result.nVolume if recog_result else 0,
                    "confidence": recog_result.nConfi if recog_result else 0,
                    "command": recog_result.pszCmd.decode('utf-8') if recog_result else "",
                    "duration_ms": recog_result.nTimer if recog_result else 0
                }
            }
        elif result == 1:  # STATUS_ERR_NEEDMORESAMPLE
            return {
                "status": "need_more_samples",
                "message": "Need more audio samples",
                "session_id": session_id
            }
        elif result == 2:  # STATUS_ERR_TIMEOUT
            return {
                "status": "timeout",
                "message": "Voice detection timeout",
                "session_id": session_id
            }
        else:
            return {
                "status": "processing",
                "message": "Processing audio samples",
                "session_id": session_id
            }

    except Exception as e:
        logger.error(f"Error processing voice samples: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process voice samples: {str(e)}")

@app.post("/voice/stop-detection/{session_id}")
async def stop_voice_detection(session_id: str):
    """Stop voice activity detection"""
    if not VOICE_RECOGNITION_AVAILABLE:
        raise HTTPException(status_code=503, detail="Voice recognition library not available")

    session_key = f"vr_session_{session_id}"

    if not hasattr(app.state, 'voice_sessions') or session_key not in app.state.voice_sessions:
        raise HTTPException(status_code=404, detail="Voice detection session not found")

    try:
        vr_lib = app.state.voice_sessions[session_key]

        # Stop recognition
        vr_lib.stop_recognition()

        # Get final result
        result = vr_lib.get_result()

        # Release resources
        vr_lib.release()

        # Remove from sessions
        del app.state.voice_sessions[session_key]

        return {
            "message": "Voice detection stopped successfully",
            "session_id": session_id,
            "final_result": {
                "volume": result.nVolume if result else 0,
                "confidence": result.nConfi if result else 0,
                "command": result.pszCmd.decode('utf-8') if result else "",
                "duration_ms": result.nTimer if result else 0
            }
        }

    except Exception as e:
        logger.error(f"Error stopping voice detection: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to stop voice detection: {str(e)}")

@app.get("/voice/detect-silence")
async def detect_silence_in_audio(
    audio_file: UploadFile = File(...),
    threshold: int = 500
):
    """Detect silence in uploaded audio file"""
    if not VOICE_RECOGNITION_AVAILABLE:
        raise HTTPException(status_code=503, detail="Voice recognition library not available")

    try:
        # Initialize voice recognition library
        vr_lib = VoiceRecognitionLibrary()
        if not vr_lib.initialize():
            raise HTTPException(status_code=500, detail="Failed to initialize voice recognition")

        # Read audio file
        audio_data = await audio_file.read()

        # Convert audio to numpy array (assuming 16-bit PCM)
        audio_array = np.frombuffer(audio_data, dtype=np.int16)

        # Detect silence
        is_silence = vr_lib.detect_silence(audio_array, threshold)
        volume = vr_lib.calculate_volume(audio_array)

        return {
            "is_silence": is_silence,
            "volume": volume,
            "threshold": threshold,
            "samples": len(audio_array),
            "duration_ms": (len(audio_array) * 1000) // 16000  # Assuming 16kHz sample rate
        }

    except Exception as e:
        logger.error(f"Error detecting silence: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to detect silence: {str(e)}")

@app.post("/voice/stream-audio-chunk")
async def stream_audio_chunk(
    session_id: str = Form(...),
    audio_chunk: UploadFile = File(...),
    chunk_index: int = Form(...),
    silence_threshold: Optional[int] = Form(500)
):
    """Stream audio chunks for real-time VAD processing"""
    if not VOICE_RECOGNITION_AVAILABLE:
        raise HTTPException(status_code=503, detail="Voice recognition library not available")

    try:
        # Read audio chunk
        audio_data = await audio_chunk.read()
        logger.info(f"Stream VAD: Received chunk {chunk_index}, size: {len(audio_data)} bytes")

        # For WebM/audio chunks, we need to extract PCM data or use a simpler volume analysis
        # Since WebM chunks contain headers and metadata, we'll use a simplified approach

        # Simple volume analysis for WebM chunks
        if len(audio_data) == 0:
            volume = 0
            is_silence = True
        else:
            # Calculate simple volume based on byte values (works for any audio format)
            byte_values = list(audio_data)
            if len(byte_values) > 0:
                # Calculate RMS-like volume from raw bytes
                sum_squares = sum((b - 128) ** 2 for b in byte_values)  # Center around 128
                volume = int((sum_squares / len(byte_values)) ** 0.5)
            else:
                volume = 0

            is_silence = volume < silence_threshold

        logger.info(f"Stream VAD: Chunk {chunk_index} - Volume: {volume}, Silence: {is_silence}")

        # Simple auto-stop logic based on calculated volume
        auto_stop_suggested = is_silence and chunk_index > 2  # After at least 2 chunks

        logger.info(f"Stream VAD: Chunk {chunk_index} - Final volume: {volume}, Silence: {is_silence}, Auto-stop: {auto_stop_suggested}")

        return {
            "session_id": session_id,
            "chunk_index": chunk_index,
            "volume": volume,
            "is_silence": is_silence,
            "auto_stop_suggested": auto_stop_suggested,
            "silence_threshold": silence_threshold,
            "samples": len(audio_data),
            "duration_ms": 1000  # Assuming 1-second chunks
        }

    except Exception as e:
        logger.error(f"Error processing audio chunk: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process audio chunk: {str(e)}")

# --- NEW: Hugging Face API Endpoint ---
# class HFPromptRequest(BaseModel):
#     prompt_text: str
#     max_length: int = 100 # Max tokens for the generated text

# class HFPromptResponse(BaseModel):
#     generated_text: str
#     error: Optional[str] = None

# @app.post("/generate-hf-text/", response_model=HFPromptResponse)
# async def generate_hf_text_endpoint(request: HFPromptRequest):
#     if not hf_model or not hf_tokenizer:
#         logger.error("Hugging Face model not loaded. Cannot process request.")
#         return JSONResponse(
#             status_code=503, # Service Unavailable
#             content={"generated_text": "", "error": "Hugging Face model is not available. Please try again later."}
#         )

#     logger.info(f"Received API request for Hugging Face model with prompt: '{request.prompt_text}'")
#     try:
#         inputs = hf_tokenizer(request.prompt_text, return_tensors="pt", padding=True, truncation=True, max_length=512) # Max input length
        
#         # Generate text
#         # For CausalLM (like GPT2):
#         if "gpt" in HF_MODEL_NAME.lower():
#             # .to("cpu") explicitly though it's default if no CUDA
#             # Use .input_ids, not just inputs
#             outputs = hf_model.generate(
#                 inputs.input_ids.to("cpu"),
#                 attention_mask=inputs.attention_mask.to("cpu"), # Pass attention_mask
#                 max_length=request.max_length + len(inputs.input_ids[0]), # max_length is total length
#                 num_return_sequences=1,
#                 pad_token_id=hf_tokenizer.eos_token_id, # Crucial for open-ended generation with GPT-2
#                 eos_token_id=hf_tokenizer.eos_token_id,
#                 do_sample=True, # To make outputs less deterministic
#                 top_k=50,
#                 top_p=0.95
#             )
#             # Decode, skipping special tokens and the prompt itself
#             generated_text = hf_tokenizer.decode(outputs[0][len(inputs.input_ids[0]):], skip_special_tokens=True)

#         # For Seq2SeqLM (like T5):
#         elif "t5" in HF_MODEL_NAME.lower():
#             outputs = hf_model.generate(
#                 inputs.input_ids.to("cpu"),
#                 attention_mask=inputs.attention_mask.to("cpu"),
#                 max_length=request.max_length, # max_length is new tokens for T5
#                 num_return_sequences=1,
#                 do_sample=True,
#                 top_k=50,
#                 top_p=0.95
#             )
#             generated_text = hf_tokenizer.decode(outputs[0], skip_special_tokens=True)
#         else:
#             # Fallback or default behavior if model type isn't specifically handled
#             # This part might need adjustment based on the actual model
#             outputs = hf_model.generate(inputs.input_ids.to("cpu"), max_length=request.max_length + len(inputs.input_ids[0]))
#             generated_text = hf_tokenizer.decode(outputs[0][len(inputs.input_ids[0]):], skip_special_tokens=True)

#         logger.info(f"Hugging Face generated text: {generated_text}")
#         return {"generated_text": generated_text.strip()}

#     except Exception as e:
#         logger.error(f"Error during Hugging Face text generation: {e}", exc_info=True)
#         return JSONResponse(
#             status_code=500,
#             content={"generated_text": "", "error": f"An internal error occurred: {str(e)}"}
#         )

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
