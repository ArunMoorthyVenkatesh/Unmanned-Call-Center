#!/usr/bin/env python3
"""
Python wrapper for the Voice Recognition C library
Provides silence detection and auto-stop functionality for voice recording
"""

import ctypes
import os
import sys
from ctypes import Structure, POINTER, c_int, c_short, c_char_p, c_void_p, c_ulong, c_char
from typing import Callable, Optional, Any
import threading
import time

# Try to import numpy, but make it optional
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    print("Warning: numpy not available, using basic array processing")

# Status codes
STATUS_SUCCESS = 0
STATUS_ERR_NEEDMORESAMPLE = 1
STATUS_ERR_TIMEOUT = 2
STATUS_START = 3
STATUS_FINISH = 4
STATUS_TIMER = 5
STATUS_STD = 6
STATUS_RESULT = 7
STATUS_SAMPLE = 8

MAX_WORD_LEN = 256

class RecogResult(Structure):
    """Recognition result structure"""
    _fields_ = [
        ("nTimer", c_ulong),        # Time in milliseconds
        ("nVolume", c_int),         # Volume 0-32767
        ("nCmdID", c_int),          # Command ID
        ("nWordDura", c_int),       # Word duration in samples
        ("nEndSil", c_int),         # End silence in samples
        ("nLatency", c_int),        # Latency in samples
        ("nConfi", c_int),          # Confidence score
        ("nSGDiff", c_int),         # SG difference
        ("nGMMappingID", c_int),    # GM mapping ID
        ("pszCmd", c_char * MAX_WORD_LEN)  # Command string
    ]

class RecordData(Structure):
    """Record data structure"""
    _fields_ = [
        ("nTimer", c_ulong),        # Recording time in milliseconds
        ("nVolume", c_int),         # Volume 0-32767
        ("psSamples", POINTER(c_short)),  # Sample data
        ("nSampleSize", c_int)      # Sample size
    ]

# Callback function types
CALLBACK_Recognition = ctypes.CFUNCTYPE(c_int, c_void_p, c_void_p, c_int, RecogResult)
CALLBACK_Record = ctypes.CFUNCTYPE(c_int, c_void_p, c_void_p, c_int, RecordData)

class VoiceRecognitionLibrary:
    """Python wrapper for the Voice Recognition C library"""

    def __init__(self, library_path: str = None):
        """Initialize the library wrapper"""
        if library_path is None:
            # Try multiple possible paths
            possible_paths = [
                "./libvoice_recognition.so",  # Current directory
                "../libvoice_recognition.so",  # Parent directory (from backend/)
                os.path.join(os.path.dirname(__file__), "libvoice_recognition.so"),  # Same dir as wrapper
                os.path.join(os.path.dirname(__file__), "..", "libvoice_recognition.so"),  # Parent of wrapper
            ]

            library_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    library_path = path
                    break

            if library_path is None:
                raise FileNotFoundError("Voice recognition library not found in any of the expected locations")
        self.lib = None
        self.handle = None
        self.record_handle = None
        self._load_library(library_path)
        self._setup_function_signatures()
        
        # Callback storage to prevent garbage collection
        self._recognition_callback = None
        self._record_callback = None
        
        # Event handlers
        self.on_recognition_result: Optional[Callable] = None
        self.on_recording_data: Optional[Callable] = None
        self.on_silence_detected: Optional[Callable] = None
        self.on_speech_detected: Optional[Callable] = None
        
    def _load_library(self, library_path: str):
        """Load the C library"""
        if not os.path.exists(library_path):
            raise FileNotFoundError(f"Library not found: {library_path}")
        
        try:
            self.lib = ctypes.CDLL(library_path)
        except OSError as e:
            raise RuntimeError(f"Failed to load library: {e}")
    
    def _setup_function_signatures(self):
        """Setup function signatures for the C library"""
        # InitEx_WithLicense
        self.lib.InitEx_WithLicense.argtypes = [c_char_p]
        self.lib.InitEx_WithLicense.restype = c_int
        
        # recogStart
        self.lib.recogStart.argtypes = [CALLBACK_Recognition, c_void_p]
        self.lib.recogStart.restype = c_void_p
        
        # addSample
        self.lib.addSample.argtypes = [c_void_p, POINTER(c_short), c_int]
        self.lib.addSample.restype = c_int
        
        # recogStop
        self.lib.recogStop.argtypes = [c_void_p]
        self.lib.recogStop.restype = c_int
        
        # getResult
        self.lib.getResult.argtypes = [c_void_p]
        self.lib.getResult.restype = RecogResult
        
        # release
        self.lib.release.argtypes = [c_void_p]
        self.lib.release.restype = c_int
        
        # recordStart
        self.lib.recordStart.argtypes = [CALLBACK_Record, c_void_p]
        self.lib.recordStart.restype = c_void_p
        
        # recordStop
        self.lib.recordStop.argtypes = [c_void_p]
        self.lib.recordStop.restype = c_int
        
        # Utility functions
        self.lib.detectSilence.argtypes = [POINTER(c_short), c_int, c_int]
        self.lib.detectSilence.restype = c_int
        
        self.lib.calculateVolume.argtypes = [POINTER(c_short), c_int]
        self.lib.calculateVolume.restype = c_int
    
    def initialize(self, license_key: str = "demo_license") -> bool:
        """Initialize the library with license"""
        result = self.lib.InitEx_WithLicense(license_key.encode('utf-8'))
        return result == STATUS_SUCCESS
    
    def _recognition_callback_wrapper(self, handler, user_data, status, result):
        """Internal callback wrapper for recognition"""
        try:
            if status == STATUS_START:
                print("Recognition started")
            elif status == STATUS_FINISH:
                print("Recognition finished")
            elif status == STATUS_TIMER:
                if self.on_recognition_result:
                    self.on_recognition_result(status, result)
            elif status == STATUS_STD:
                print("Speech detected")
                if self.on_speech_detected:
                    self.on_speech_detected(result)
            elif status == STATUS_RESULT:
                print(f"Recognition result: {result.pszCmd.decode('utf-8')}")
                if result.pszCmd.decode('utf-8') == "AUTO_STOP_DETECTED":
                    if self.on_silence_detected:
                        self.on_silence_detected(result)
                if self.on_recognition_result:
                    self.on_recognition_result(status, result)
            elif status == STATUS_ERR_TIMEOUT:
                print("Recognition timeout")
                if self.on_recognition_result:
                    self.on_recognition_result(status, result)
                    
        except Exception as e:
            print(f"Error in recognition callback: {e}")
        
        return 0
    
    def _record_callback_wrapper(self, handler, user_data, status, record_data):
        """Internal callback wrapper for recording"""
        try:
            if status == STATUS_START:
                print("Recording started")
            elif status == STATUS_FINISH:
                print("Recording finished")
            elif status == STATUS_TIMER:
                if self.on_recording_data:
                    self.on_recording_data(status, record_data)
            elif status == STATUS_SAMPLE:
                if self.on_recording_data:
                    self.on_recording_data(status, record_data)
                    
        except Exception as e:
            print(f"Error in record callback: {e}")
        
        return 0
    
    def start_recognition(self) -> bool:
        """Start voice recognition"""
        if self.handle:
            return False
            
        self._recognition_callback = CALLBACK_Recognition(self._recognition_callback_wrapper)
        self.handle = self.lib.recogStart(self._recognition_callback, None)
        return self.handle is not None
    
    def add_samples(self, audio_data) -> int:
        """Add audio samples for processing"""
        if not self.handle:
            return STATUS_ERR_TIMEOUT

        if NUMPY_AVAILABLE and hasattr(audio_data, 'dtype'):
            # Handle numpy array
            if audio_data.dtype != np.int16:
                audio_data = audio_data.astype(np.int16)
            samples_ptr = audio_data.ctypes.data_as(POINTER(c_short))
            num_samples = len(audio_data)
        else:
            # Handle raw bytes or list
            if isinstance(audio_data, bytes):
                # Ensure buffer size is multiple of 2 (16-bit samples)
                if len(audio_data) % 2 != 0:
                    audio_data = audio_data[:-1]  # Remove last byte if odd

                # Convert bytes to array of shorts
                import struct
                try:
                    audio_data = struct.unpack(f'<{len(audio_data)//2}h', audio_data)
                except struct.error as e:
                    print(f"Warning: struct unpack error: {e}, using zeros")
                    audio_data = [0] * (len(audio_data) // 2)

            # Convert to ctypes array
            samples_array = (c_short * len(audio_data))(*audio_data)
            samples_ptr = ctypes.cast(samples_array, POINTER(c_short))
            num_samples = len(audio_data)

        return self.lib.addSample(self.handle, samples_ptr, num_samples)
    
    def stop_recognition(self) -> bool:
        """Stop voice recognition"""
        if not self.handle:
            return False
            
        result = self.lib.recogStop(self.handle)
        return result == STATUS_SUCCESS
    
    def get_result(self) -> Optional[RecogResult]:
        """Get recognition result"""
        if not self.handle:
            return None
            
        return self.lib.getResult(self.handle)
    
    def release(self) -> bool:
        """Release resources"""
        if not self.handle:
            return True
            
        result = self.lib.release(self.handle)
        self.handle = None
        self._recognition_callback = None
        return result == STATUS_SUCCESS
    
    def start_recording(self) -> bool:
        """Start recording"""
        if self.record_handle:
            return False
            
        self._record_callback = CALLBACK_Record(self._record_callback_wrapper)
        self.record_handle = self.lib.recordStart(self._record_callback, None)
        return self.record_handle is not None
    
    def stop_recording(self) -> bool:
        """Stop recording"""
        if not self.record_handle:
            return False
            
        result = self.lib.recordStop(self.record_handle)
        self.record_handle = None
        self._record_callback = None
        return result == STATUS_SUCCESS
    
    def detect_silence(self, audio_data, threshold: int = 500) -> bool:
        """Detect silence in audio data"""
        if NUMPY_AVAILABLE and hasattr(audio_data, 'dtype'):
            # Handle numpy array
            if audio_data.dtype != np.int16:
                audio_data = audio_data.astype(np.int16)
            samples_ptr = audio_data.ctypes.data_as(POINTER(c_short))
            num_samples = len(audio_data)
        else:
            # Handle raw bytes or list
            if isinstance(audio_data, bytes):
                # Ensure buffer size is multiple of 2 (16-bit samples)
                if len(audio_data) % 2 != 0:
                    audio_data = audio_data[:-1]  # Remove last byte if odd

                import struct
                try:
                    audio_data = struct.unpack(f'<{len(audio_data)//2}h', audio_data)
                except struct.error as e:
                    print(f"Warning: struct unpack error in detect_silence: {e}, using zeros")
                    audio_data = [0] * (len(audio_data) // 2)

            samples_array = (c_short * len(audio_data))(*audio_data)
            samples_ptr = ctypes.cast(samples_array, POINTER(c_short))
            num_samples = len(audio_data)

        result = self.lib.detectSilence(samples_ptr, num_samples, threshold)
        return result == 1

    def calculate_volume(self, audio_data) -> int:
        """Calculate volume of audio data"""
        if NUMPY_AVAILABLE and hasattr(audio_data, 'dtype'):
            # Handle numpy array
            if audio_data.dtype != np.int16:
                audio_data = audio_data.astype(np.int16)
            samples_ptr = audio_data.ctypes.data_as(POINTER(c_short))
            num_samples = len(audio_data)
        else:
            # Handle raw bytes or list
            if isinstance(audio_data, bytes):
                # Ensure buffer size is multiple of 2 (16-bit samples)
                if len(audio_data) % 2 != 0:
                    audio_data = audio_data[:-1]  # Remove last byte if odd

                import struct
                try:
                    audio_data = struct.unpack(f'<{len(audio_data)//2}h', audio_data)
                except struct.error as e:
                    print(f"Warning: struct unpack error in calculate_volume: {e}, using zeros")
                    audio_data = [0] * (len(audio_data) // 2)

            samples_array = (c_short * len(audio_data))(*audio_data)
            samples_ptr = ctypes.cast(samples_array, POINTER(c_short))
            num_samples = len(audio_data)

        return self.lib.calculateVolume(samples_ptr, num_samples)

# Example usage and testing
if __name__ == "__main__":
    # This would be used for testing the wrapper
    print("Voice Recognition Library Wrapper")
    print("This module should be imported and used in your main application")
